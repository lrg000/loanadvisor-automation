"""业务逻辑源自 appium自动化测试_备份.py"""
from __future__ import annotations

import json
import os
import random
import string
import subprocess
import time
import uuid

import pymysql
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from loanadvisor.core.config import settings
from loanadvisor.core.login_session import LOGIN_DATA

from loanadvisor.helpers.native.interactions import swipe_up
from loanadvisor.helpers.native.permissions import handle_permission_popup
from loanadvisor.helpers.webview.clicks import click_any_target_text, wait_for_h5_text
from loanadvisor.helpers.webview.switcher import switch_to_real_webview

swipe_up_h5 = swipe_up

def swipe_up_h5(driver, distance=350):
    """H5 页面内上滑"""
    driver.execute_script(f"window.scrollBy(0, {distance});")
    time.sleep(0.4)
    print("H5 上滑")


def h5_scroll_to_label(driver, label):
    """滚动到指定 label 所在表单项"""
    driver.execute_script(
        """
        const label = arguments[0];
        for (const el of document.querySelectorAll('label, div, span, p')) {
            const text = (el.innerText || '').trim();
            if (!text.includes(label)) continue;
            if (text.length > label.length + 20) continue;
            el.scrollIntoView({block: 'center', behavior: 'instant'});
            return true;
        }
        return false;
        """,
        label,
    )
    time.sleep(0.5)


def h5_get_field_container_js():
    return """
        function getFieldRow(labelKeyword) {
            for (const el of document.querySelectorAll('label, div, span, p')) {
                const t = (el.innerText || '').trim();
                if (!t.includes(labelKeyword)) continue;
                if (t.length > labelKeyword.length + 25) continue;

                let node = el;
                for (let i = 0; i < 10; i++) {
                    if (!node) break;
                    const ct = (node.innerText || '').trim();
                    const r = node.getBoundingClientRect();
                    if (!ct.includes(labelKeyword)) {
                        node = node.parentElement;
                        continue;
                    }
                    if (r.height < 45 || r.height > 280 || r.width < 80) {
                        node = node.parentElement;
                        continue;
                    }
                    const lines = ct.split('\\n').map(s => s.trim()).filter(Boolean);
                    if (lines.length >= 2 || ct.includes('Select ')) {
                        return node;
                    }
                    node = node.parentElement;
                }
            }
            return null;
        }
    """


def h5_is_select_empty(driver, label, placeholder):
    """按 label 判断下拉框是否未填（只检查该字段容器内是否仍显示 Select xxx）"""
    return driver.execute_script(
        h5_get_field_container_js()
        + """
        const label = arguments[0];
        const placeholder = arguments[1];
        const row = getFieldRow(label);
        if (!row) return true;
        return (row.innerText || '').includes(placeholder);
        """,
        label,
        placeholder,
    )


def h5_is_text_empty(driver, label_keyword):
    """按 label 判断文本框是否未填"""
    return driver.execute_script(
        h5_get_field_container_js()
        + """
        const label = arguments[0];
        const row = getFieldRow(label);
        if (!row) return true;
        const inp = row.querySelector('input, textarea');
        if (inp) return !(inp.value || '').trim();
        return true;
        """,
        label_keyword,
    )


def h5_hide_keyboard(driver):
    """收起键盘，避免遮挡下拉弹窗"""
    try:
        driver.hide_keyboard()
    except Exception:
        pass
    try:
        driver.execute_script(
            "if (document.activeElement) document.activeElement.blur();"
        )
    except Exception:
        pass
    time.sleep(0.3)


def h5_get_text_value(driver, label):
    """读取文本框当前值"""
    return driver.execute_script(
        h5_get_field_container_js()
        + """
        const label = arguments[0];
        const row = getFieldRow(label);
        if (row) {
            const inp = row.querySelector('input, textarea');
            if (inp) return (inp.value || '').trim();
        }
        for (const el of document.querySelectorAll('label, div, span, p')) {
            const text = (el.innerText || '').trim();
            if (!text.includes(label) || text.length > label.length + 25) continue;
            let node = el;
            for (let i = 0; i < 8; i++) {
                if (!node) break;
                const inp = node.querySelector('input, textarea');
                if (inp) return (inp.value || '').trim();
                node = node.parentElement;
            }
        }
        for (const inp of document.querySelectorAll('input, textarea')) {
            const ph = (inp.placeholder || '').toLowerCase();
            if (ph.includes(label.toLowerCase())) return (inp.value || '').trim();
        }
        return '';
        """,
        label,
    ) or ""


def h5_field_shows_placeholder(driver, label, placeholder):
    """该下拉字段行内是否仍显示 Select xxx"""
    return driver.execute_script(
        """
        const label = arguments[0];
        const ph = arguments[1];
        for (const el of document.querySelectorAll('label, div, span, p')) {
            const t = (el.innerText || '').trim();
            if (!t.includes(label) || t.length > label.length + 60) continue;
            let node = el;
            for (let i = 0; i < 10; i++) {
                if (!node) break;
                const ct = node.innerText || '';
                if (ct.includes(label) && ct.includes(ph)) return true;
                node = node.parentElement;
            }
        }
        return false;
        """,
        label,
        placeholder,
    )


def h5_select_has_value(driver, label, expected_value):
    """
    下拉是否已选中：字段行内必须出现 expected_value（如 Single），
    不能仅凭 placeholder 不可见就判断已填。
    """
    return driver.execute_script(
        """
        const label = arguments[0];
        const expected = (arguments[1] || '').trim().toLowerCase();
        if (!expected) return false;

        function norm(s) { return (s || '').trim().toLowerCase(); }
        function matchValue(line, exp) {
            const l = norm(line);
            return l === exp || l.includes(exp) || exp.includes(l);
        }

        for (const el of document.querySelectorAll('label, div, span, p')) {
            const text = (el.innerText || '').trim();
            if (!text.includes(label)) continue;
            if (text.length > label.length + 80) continue;

            let node = el;
            for (let i = 0; i < 10; i++) {
                if (!node) break;
                const ct = (node.innerText || '').trim();
                if (!ct.includes(label)) {
                    node = node.parentElement;
                    continue;
                }
                const lines = ct.split('\\n').map(s => s.trim()).filter(Boolean);
                for (const line of lines) {
                    if (norm(line).includes(norm(label))) continue;
                    if (line.startsWith('Select ')) continue;
                    if (line.includes('Invalid')) continue;
                    if (matchValue(line, expected)) return true;
                }
                node = node.parentElement;
            }
        }

        // 兜底：label 附近可见区域出现 expected 文案
        let anchorY = null;
        for (const el of document.querySelectorAll('label, div, span, p')) {
            const t = (el.innerText || '').trim();
            if (t.includes(label) && t.length <= label.length + 25) {
                anchorY = el.getBoundingClientRect().top;
                break;
            }
        }
        if (anchorY !== null) {
            for (const el of document.querySelectorAll('div, span, p')) {
                const t = (el.innerText || '').trim();
                if (!t || t.includes('\\n')) continue;
                if (matchValue(t, expected)) {
                    const y = el.getBoundingClientRect().top;
                    if (Math.abs(y - anchorY) < 150) return true;
                }
            }
        }
        return false;
        """,
        label,
        expected_value,
    )


def h5_modal_is_open(driver, modal_title=None):
    """检测底部 sheet 是否打开：优先看遮罩层，避免与表单 label 混淆"""
    return driver.execute_script(
        """
        const title = arguments[0];
        for (const el of document.querySelectorAll(
            '[class*="overlay"], [class*="mask"], [class*="modal"], [class*="popup"], [class*="sheet"]'
        )) {
            const st = window.getComputedStyle(el);
            if (st.display === 'none' || st.visibility === 'hidden') continue;
            const op = parseFloat(st.opacity || '1');
            if (op < 0.08) continue;
            const r = el.getBoundingClientRect();
            if (r.width >= window.innerWidth * 0.85 && r.height >= window.innerHeight * 0.2) {
                return true;
            }
        }
        if (!title) return false;
        for (const el of document.querySelectorAll('div, span, p, h1, h2, h3')) {
            const t = (el.innerText || '').trim();
            if (t !== title) continue;
            const r = el.getBoundingClientRect();
            if (r.top < window.innerHeight * 0.38 || r.top > window.innerHeight * 0.88) continue;
            let hasOptionBelow = false;
            for (const opt of document.querySelectorAll('div, span, li, p')) {
                const ot = (opt.innerText || '').trim();
                const or = opt.getBoundingClientRect();
                if (!ot || ot === title || ot.startsWith('Select ')) continue;
                if (ot.length > 40) continue;
                if (or.top > r.bottom && or.top < r.bottom + 350) {
                    hasOptionBelow = true;
                    break;
                }
            }
            if (hasOptionBelow) return true;
        }
        return false;
        """,
        modal_title,
    )


def h5_tap_webview_element(driver, element):
    """WebView 元素点击：Selenium click + 坐标 tap 双保险"""
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center', behavior:'instant'});", element
        )
        time.sleep(0.2)
    except Exception:
        pass
    try:
        WebDriverWait(driver, 2).until(EC.element_to_be_clickable(element))
        element.click()
        return True
    except Exception:
        pass
    try:
        rect = element.rect
        x = rect["x"] + rect["width"] // 2
        y = rect["y"] + rect["height"] // 2
        driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False


def h5_click_by_exact_text(driver, text, timeout=5, in_bottom_sheet=False):
    """
    点击页面上精确匹配文本的元素（用于打开下拉、点选选项）
    in_bottom_sheet=True 时只在屏幕下半部分查找（弹窗选项）
    """
    end_time = time.time() + timeout

    while time.time() < end_time:
        clicked = driver.execute_script(
            """
            const text = arguments[0];
            const inSheet = arguments[1];
            for (const el of document.querySelectorAll('div, span, p, label, li')) {
                const t = (el.innerText || '').trim();
                if (t !== text) continue;
                const r = el.getBoundingClientRect();
                if (r.width < 8 || r.height < 8) continue;
                if (inSheet && r.top < window.innerHeight * 0.2) continue;
                if (!inSheet && r.top > window.innerHeight * 0.92) continue;
                el.scrollIntoView({block: 'center', behavior: 'instant'});
                el.click();
                const row = el.closest('div') || el;
                row.click();
                return true;
            }
            return false;
            """,
            text,
            in_bottom_sheet,
        )
        if clicked:
            return True

        try:
            el = WebDriverWait(driver, 1).until(
                EC.presence_of_element_located(
                    (By.XPATH, f"//*[normalize-space()='{text}']")
                )
            )
            if in_bottom_sheet:
                y = el.location.get("y", 0)
                size = driver.get_window_size()
                if y < size["height"] * 0.2:
                    time.sleep(0.3)
                    continue
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center', behavior:'instant'});", el
            )
            try:
                WebDriverWait(driver, 1).until(EC.element_to_be_clickable(el))
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            pass

        time.sleep(0.3)

    return False


def h5_tap_at(driver, x, y):
    """WebView 视口坐标点击"""
    ix, iy = int(x), int(y)
    try:
        driver.execute_script("mobile: clickGesture", {"x": ix, "y": iy})
    except Exception:
        pass
    try:
        return bool(
            driver.execute_script(
                """
                const x = arguments[0], y = arguments[1];
                const el = document.elementFromPoint(x, y);
                if (!el) return false;
                el.click();
                return true;
                """,
                ix,
                iy,
            )
        )
    except Exception:
        return False


def h5_vue_click_element(driver, element):
    """Vue/H5 组件点击：Touch + Mouse 事件 + 父节点冒泡"""
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center', behavior:'instant'});", element
        )
        time.sleep(0.2)
        driver.execute_script(
            """
            const el = arguments[0];
            const r = el.getBoundingClientRect();
            const x = r.left + r.width / 2;
            const y = r.top + r.height / 2;

            function fireMouse(type) {
                el.dispatchEvent(new MouseEvent(type, {
                    bubbles: true, cancelable: true, view: window,
                    clientX: x, clientY: y,
                }));
            }
            try {
                el.dispatchEvent(new TouchEvent('touchstart', {
                    bubbles: true, cancelable: true,
                    touches: [{ clientX: x, clientY: y }],
                }));
                el.dispatchEvent(new TouchEvent('touchend', {
                    bubbles: true, cancelable: true,
                    touches: [],
                }));
            } catch (e) {}

            fireMouse('mousedown');
            fireMouse('mouseup');
            fireMouse('click');
            el.click();

            let p = el;
            for (let i = 0; i < 5; i++) {
                if (!p.parentElement) break;
                p = p.parentElement;
                p.click();
            }
            return true;
            """,
            element,
        )
        return True
    except Exception:
        return False


def h5_w3c_tap_element(driver, element):
    """W3C PointerInput 点击元素中心（WebView 最稳）"""
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center', behavior:'instant'});", element
        )
        time.sleep(0.25)
        actions = ActionBuilder(driver)
        finger = PointerInput(interaction.POINTER_TOUCH, "finger")
        actions.add_action(finger.create_pointer_move(origin=element))
        actions.add_action(finger.create_pointer_down(button=0))
        actions.add_action(finger.create_pointer_up(button=0))
        actions.perform()
        return True
    except Exception:
        return False


def h5_native_tap_element(driver, element):
    """NATIVE 层按 WebView 偏移 tap（CSS 坐标 → 屏幕坐标）"""
    ctx = driver.current_context
    try:
        rect = element.rect
        cx = rect["x"] + rect["width"] / 2
        cy = rect["y"] + rect["height"] / 2

        driver.switch_to.context("NATIVE_APP")
        webview = None
        for wv in driver.find_elements(AppiumBy.CLASS_NAME, "android.webkit.WebView"):
            try:
                if wv.is_displayed():
                    webview = wv
                    break
            except Exception:
                continue
        if not webview:
            return False

        wr = webview.rect
        abs_x = int(wr["x"] + cx)
        abs_y = int(wr["y"] + cy)
        driver.execute_script("mobile: clickGesture", {"x": abs_x, "y": abs_y})
        return True
    except Exception:
        return False
    finally:
        if driver.current_context != ctx:
            try:
                driver.switch_to.context(ctx)
            except Exception:
                pass


def h5_repay_details_visible(driver):
    """是否已进入 Repayment Details 页"""
    try:
        return bool(
            driver.execute_script(
                """
                const t = document.body ? document.body.innerText : '';
                const href = (window.location.href || '').toLowerCase();
                return t.includes('Repayment Details')
                    || t.includes('Repayment method')
                    || href.includes('detail');
                """
            )
        )
    except Exception:
        return False


def h5_find_repay_loan_elements(driver):
    """查找 Repay Loan 按钮元素（精确文案，自上而下排序）"""
    els = driver.find_elements(
        By.XPATH,
        "//*[normalize-space(text())='Repay Loan' or normalize-space()='Repay Loan']",
    )
    screen_h = driver.get_window_size()["height"]
    visible = []
    for el in els:
        try:
            if not el.is_displayed():
                continue
            r = el.rect
            if r["height"] < 10 or r["width"] < 40:
                continue
            if r["y"] > screen_h * 0.92:
                continue
            visible.append((el, r["y"], r["width"] * r["height"]))
        except Exception:
            continue
    visible.sort(key=lambda x: (x[1], -x[2]))
    return [x[0] for x in visible]


def h5_click_text_and_parents(driver, text, timeout=4, bottom_sheet_only=False):
    """
    点击匹配文本的元素及其父节点（早期能打开下拉的做法）
    bottom_sheet_only=True 时只在屏幕下半部匹配（用于弹窗选项）
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        clicked = driver.execute_script(
            """
            const target = arguments[0];
            const bottomOnly = arguments[1];

            for (const el of document.querySelectorAll('body *')) {
                const t = (el.innerText || el.textContent || '').trim();
                const ph = (el.placeholder || el.getAttribute('placeholder') || '').trim();
                const hit = t === target || ph === target ||
                    (t.length <= target.length + 20 && t.includes(target));
                if (!hit) continue;

                const r = el.getBoundingClientRect();
                if (r.width < 8 || r.height < 5) continue;
                if (r.top < 0 || r.bottom > window.innerHeight + 5) continue;
                if (bottomOnly && r.top < window.innerHeight * 0.22) continue;
                if (!bottomOnly && r.top > window.innerHeight * 0.95) continue;

                el.scrollIntoView({block: 'center', behavior: 'instant'});
                el.click();
                let p = el;
                for (let i = 0; i < 5; i++) {
                    if (!p.parentElement) break;
                    p = p.parentElement;
                    p.click();
                }
                return true;
            }
            return false;
            """,
            text,
            bottom_sheet_only,
        )
        if clicked:
            return True

        try:
            els = driver.find_elements(
                By.XPATH, f"//*[contains(normalize-space(), '{text}')]"
            )
            screen_h = driver.get_window_size()["height"]
            for el in els:
                y = el.location.get("y", 0)
                if bottom_sheet_only and y < screen_h * 0.22:
                    continue
                if (el.text or "").strip() and len((el.text or "").strip()) > len(text) + 30:
                    continue
                if h5_tap_webview_element(driver, el):
                    return True
        except Exception:
            pass

        time.sleep(0.3)
    return False


def h5_open_select_dropdown(driver, label, placeholder):
    """WebView：点击选项框打开底部弹窗（多策略，兼容早期可用逻辑）"""
    h5_hide_keyboard(driver)
    h5_scroll_to_label(driver, label)
    time.sleep(0.3)

    # 策略1：直接点 placeholder 文案（早期验证可行）
    if h5_click_text_and_parents(driver, placeholder, timeout=4):
        time.sleep(0.6)
        print(f"已打开选择框: {label} ({placeholder})")
        return True

    # 策略2：点 input 的 placeholder 属性所在行
    tapped = driver.execute_script(
        """
        const ph = arguments[0];
        const label = arguments[1];
        for (const inp of document.querySelectorAll('input, textarea')) {
            const attr = (inp.placeholder || inp.getAttribute('placeholder') || '').trim();
            if (attr !== ph && !attr.includes(ph.replace(/^Select\\s+/i, ''))) continue;
            const row = inp.closest('div') || inp.parentElement || inp;
            row.scrollIntoView({block: 'center', behavior: 'instant'});
            row.click();
            inp.click();
            return true;
        }
        for (const el of document.querySelectorAll('div, span, p, label')) {
            const t = (el.innerText || '').trim();
            if (!t.includes(label)) continue;
            let node = el;
            for (let i = 0; i < 8; i++) {
                if (!node) break;
                const ct = node.innerText || '';
                const r = node.getBoundingClientRect();
                if (ct.includes(label) && ct.includes('Select') && r.height >= 30 && r.width >= 120) {
                    node.scrollIntoView({block: 'center', behavior: 'instant'});
                    node.click();
                    return true;
                }
                node = node.parentElement;
            }
        }
        return false;
        """,
        placeholder,
        label,
    )
    if tapped:
        time.sleep(0.6)
        print(f"已打开选择框(行点击): {label}")
        return True

    # 策略3：复用 click_any_target_text
    try:
        click_any_target_text(driver, [placeholder], timeout=3)
        time.sleep(0.6)
        print(f"已打开选择框(fallback): {label}")
        return True
    except Exception:
        pass

    print(f"⚠️ 无法打开选择框: {label}（placeholder: {placeholder}）")
    return False


def h5_click_select_option(driver, option_text, modal_title=None, timeout=10):
    """WebView 底部弹窗：点击选项行，不依赖弹窗标题检测"""
    end_time = time.time() + timeout
    modal_titles = [
        "Marital Status", "Education Level", "Purpose of Loan", "State",
        "Employment Type", "Work Experience", "Salary Credit Day", "Monthly Income",
        "Relationship with you", "Relationship",
        "Primary Reference", "Secondary Reference", "Full Name", "Mobile",
    ]

    time.sleep(0.5)

    while time.time() < end_time:
        if h5_click_text_and_parents(driver, option_text, timeout=2, bottom_sheet_only=True):
            time.sleep(0.6)
            print(f"已选择: {option_text}")
            return option_text

        tap = driver.execute_script(
            """
            const wanted = (arguments[0] || '').trim().toLowerCase();
            const titles = new Set(arguments[1]);

            function match(t) {
                const a = t.trim().toLowerCase();
                return a === wanted || a.includes(wanted) || wanted.includes(a);
            }

            let best = null;
            for (const el of document.querySelectorAll('div, span, li, p, label')) {
                const r = el.getBoundingClientRect();
                if (r.top < window.innerHeight * 0.28) continue;
                if (r.height < 14 || r.height > 75 || r.width < 60) continue;

                const lines = (el.innerText || '').trim().split('\\n').map(s => s.trim()).filter(Boolean);
                if (lines.length !== 1) continue;
                const t = lines[0];
                if (!t || titles.has(t) || t.startsWith('Select ')) continue;
                if (!match(t)) continue;

                // 向上找选项行（含 radio 的整行）
                let row = el;
                for (let i = 0; i < 8; i++) {
                    const p = row.parentElement;
                    if (!p) break;
                    const pr = p.getBoundingClientRect();
                    if (pr.height >= 40 && pr.height <= 100 && pr.width > window.innerWidth * 0.45) {
                        row = p;
                    }
                }
                const rr = row.getBoundingClientRect();
                const score = rr.height;
                if (!best || score < best.score) {
                    best = {
                        x: rr.left + rr.width * 0.45,
                        y: rr.top + rr.height / 2,
                        text: t,
                        score: score
                    };
                }
            }
            return best;
            """,
            option_text,
            modal_titles,
        )

        if tap:
            h5_tap_at(driver, tap["x"], tap["y"])
            time.sleep(0.6)
            print(f"已选择: {tap['text']}")
            return tap["text"]

        time.sleep(0.4)

    print(f"⚠️ 未能选择选项: {option_text}")
    return None


def h5_click_select_field(driver, label, placeholder):
    """兼容旧调用：打开下拉"""
    return h5_open_select_dropdown(driver, label, placeholder)


def h5_pick_select_option(driver, option_text=None):
    """兼容旧调用：在弹窗中点选"""
    return h5_click_select_option(driver, option_text or "")


def h5_dismiss_modal_if_open(driver):
    """若底部弹窗仍打开，点击遮罩关闭"""
    driver.execute_script(
        """
        const overlays = document.querySelectorAll(
            '[class*="overlay"], [class*="mask"], [class*="popup"], [class*="modal"]'
        );
        for (const el of overlays) {
            const r = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            if (r.width >= window.innerWidth * 0.9 && r.height >= window.innerHeight * 0.5
                && (style.position === 'fixed' || style.position === 'absolute')) {
                el.click();
                return true;
            }
        }
        return false;
        """
    )
    time.sleep(0.3)


def h5_fill_text_field(driver, label_keyword, value, scroll=True):
    """填写文本输入框：先清空再赋值，只用一种方式，避免重复输入"""
    if scroll:
        h5_scroll_to_label(driver, label_keyword)

    filled = driver.execute_script(
        h5_get_field_container_js()
        + """
        const label = arguments[0];
        const value = arguments[1];
        let inp = null;
        const row = getFieldRow(label);
        if (row) inp = row.querySelector('input, textarea');
        if (!inp) {
            for (const el of document.querySelectorAll('input, textarea')) {
                const ph = (el.placeholder || '').toLowerCase();
                if (ph.includes(label.toLowerCase())) { inp = el; break; }
            }
        }
        if (!inp) return false;

        inp.scrollIntoView({block: 'center', behavior: 'instant'});
        inp.focus();
        inp.click();
        const proto = inp.tagName === 'TEXTAREA'
            ? window.HTMLTextAreaElement.prototype
            : window.HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, 'value');
        if (setter && setter.set) {
            setter.set.call(inp, '');
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            setter.set.call(inp, value);
        } else {
            inp.value = value;
        }
        inp.dispatchEvent(new Event('input', {bubbles: true}));
        inp.dispatchEvent(new Event('change', {bubbles: true}));
        inp.blur();
        return (inp.value || '').trim() === value;
        """,
        label_keyword,
        value,
    )

    if not filled:
        try:
            inp = driver.find_element(
                By.XPATH,
                f"//*[contains(normalize-space(), '{label_keyword}')]/following::input[1]"
            )
            inp.click()
            driver.execute_script("arguments[0].value='';", inp)
            inp.clear()
            inp.send_keys(value)
            filled = (inp.get_attribute("value") or "").strip() == value
        except Exception:
            pass

    if filled:
        print(f"已填写 {label_keyword}: {value}")
    return filled


def h5_click_success_confirm(driver, timeout=15):
    """点击 Success 弹窗底部 Confirm 按钮（Vue div，通常无 onclick 属性）"""
    end_time = time.time() + timeout
    while time.time() < end_time:
        clicked = driver.execute_script(
            """
            let best = null;
            let bestBottom = -1;

            for (const el of document.querySelectorAll('button, a, div, span')) {
                const text = (el.innerText || '').trim();
                if (text !== 'Confirm') continue;
                const rect = el.getBoundingClientRect();
                if (rect.width < 60 || rect.height < 18) continue;
                if (rect.bottom > bestBottom) {
                    bestBottom = rect.bottom;
                    best = el;
                }
            }

            if (best) {
                best.scrollIntoView({block: 'center', behavior: 'instant'});
                best.click();
                let p = best;
                for (let i = 0; i < 4; i++) {
                    if (!p.parentElement) break;
                    p = p.parentElement;
                    p.click();
                }
                return true;
            }
            return false;
            """
        )
        if clicked:
            print("✅ 已点击 Success 弹窗 Confirm 按钮")
            return True

        if h5_click_text_and_parents(driver, "Confirm", timeout=2):
            print("✅ 已通过 fallback 点击 Confirm 按钮")
            return True

        time.sleep(0.5)

    return False


def h5_click_repay_loan_button(driver, timeout=20):
    """点击还款页 Repay Loan 按钮，并验证进入 Repayment Details"""
    end_time = time.time() + timeout
    strategies = [
        ("W3C Touch", h5_w3c_tap_element),
        ("Vue 事件", h5_vue_click_element),
        ("Selenium click", h5_tap_webview_element),
        ("Native 坐标", h5_native_tap_element),
    ]

    while time.time() < end_time:
        clicked_js = driver.execute_script(
            """
            const target = 'Repay Loan';
            const candidates = [];
            for (const el of document.querySelectorAll('button, a, div, span, p')) {
                const t = (el.innerText || el.textContent || '').trim();
                if (t !== target) continue;
                let node = el.closest('button, a, [role="button"]') || el;
                const r = node.getBoundingClientRect();
                if (r.width < 60 || r.height < 14) continue;
                if (r.top < 0 || r.bottom > window.innerHeight * 0.92) continue;
                candidates.push({ top: r.top, node });
            }
            candidates.sort((a, b) => a.top - b.top);
            if (!candidates.length) return false;

            function vueTap(node) {
                node.scrollIntoView({ block: 'center', behavior: 'instant' });
                const r = node.getBoundingClientRect();
                const x = r.left + r.width / 2;
                const y = r.top + r.height / 2;
                try {
                    node.dispatchEvent(new TouchEvent('touchstart', { bubbles: true, cancelable: true }));
                    node.dispatchEvent(new TouchEvent('touchend', { bubbles: true, cancelable: true }));
                } catch (e) {}
                node.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                node.click();
                let p = node;
                for (let i = 0; i < 5; i++) {
                    if (!p.parentElement) break;
                    p = p.parentElement;
                    p.click();
                }
            }

            vueTap(candidates[0].node);

            // 兜底：点击包含 Repay Loan 的整张 card
            let card = candidates[0].node;
            for (let i = 0; i < 8 && card; i++) {
                const ct = (card.innerText || '').trim();
                const cr = card.getBoundingClientRect();
                if (ct.includes('Repayment Amount') && ct.includes('Repay Loan')
                    && cr.height > 100 && cr.height < 500) {
                    vueTap(card);
                    break;
                }
                card = card.parentElement;
            }
            return true;
            """
        )
        if clicked_js:
            time.sleep(1.2)
            if h5_repay_details_visible(driver):
                print("✅ 已通过 JS 点击 Repay Loan，已进入详情页")
                return True

        elements = h5_find_repay_loan_elements(driver)
        for el in elements[:2]:
            for name, fn in strategies:
                try:
                    fn(driver, el)
                except Exception:
                    pass
                time.sleep(1.2)
                if h5_repay_details_visible(driver):
                    print(f"✅ 已通过 {name} 点击 Repay Loan，已进入详情页")
                    return True

        try:
            if elements:
                ActionChains(driver).move_to_element(elements[0]).click().perform()
                time.sleep(1.2)
                if h5_repay_details_visible(driver):
                    print("✅ 已通过 ActionChains 点击 Repay Loan，已进入详情页")
                    return True
        except Exception:
            pass

        time.sleep(0.6)

    print("⚠️ Repay Loan 多次点击后仍未进入 Repayment Details")
    return False


def h5_click_first_text(driver, text, timeout=10):
    """点击页面上第一个匹配文案的可点击元素（自上而下，多个同名时只点第一个）"""
    end_time = time.time() + timeout
    while time.time() < end_time:
        clicked = driver.execute_script(
            """
            const target = arguments[0];
            const candidates = [];

            for (const el of document.querySelectorAll('a, button, div, span, p, li')) {
                const t = (el.innerText || el.textContent || '').trim();
                if (!t.includes(target)) continue;

                const lines = t.split('\\n').map(s => s.trim()).filter(Boolean);
                const hit = lines.some(l => l === target || l.includes(target));
                if (!hit) continue;
                if (t.length > target.length + 50) continue;

                const r = el.getBoundingClientRect();
                if (r.width < 20 || r.height < 8) continue;
                if (r.top < -5 || r.top > window.innerHeight + 5) continue;

                candidates.push({ el, top: r.top });
            }

            candidates.sort((a, b) => a.top - b.top);
            if (!candidates.length) return false;

            const el = candidates[0].el;
            el.scrollIntoView({block: 'center', behavior: 'instant'});
            el.click();
            let p = el;
            for (let i = 0; i < 4; i++) {
                if (!p.parentElement) break;
                p = p.parentElement;
                p.click();
            }
            return true;
            """,
            text,
        )
        if clicked:
            print(f"✅ 已点击第一个: {text}")
            return True
        time.sleep(0.5)
    return False


def h5_click_bottom_button(driver, text, timeout=15):
    """点击页面最底部、文案完全匹配的 H5 按钮（如 Repay / Next / Confirm）"""
    end_time = time.time() + timeout
    while time.time() < end_time:
        clicked = driver.execute_script(
            """
            const wanted = arguments[0];
            let best = null;
            let bestBottom = -1;

            for (const el of document.querySelectorAll('button, a, div, span')) {
                const t = (el.innerText || '').trim();
                if (t !== wanted) continue;
                const r = el.getBoundingClientRect();
                if (r.width < 50 || r.height < 18) continue;
                if (r.bottom > bestBottom) {
                    bestBottom = r.bottom;
                    best = el;
                }
            }

            if (best) {
                best.scrollIntoView({block: 'center', behavior: 'instant'});
                best.click();
                let p = best;
                for (let i = 0; i < 4; i++) {
                    if (!p.parentElement) break;
                    p = p.parentElement;
                    p.click();
                }
                return true;
            }
            return false;
            """,
            text,
        )
        if clicked:
            print(f"✅ 已点击底部按钮: {text}")
            return True

        time.sleep(0.5)
    return False


def h5_click_form_next(driver):
    """点击 Basic info 页面底部 Next 提交按钮"""
    clicked = driver.execute_script(
        """
        const buttons = document.querySelectorAll('button, a, div, span');
        let best = null;
        let bestBottom = -1;

        for (const el of buttons) {
            const text = (el.innerText || '').trim();
            if (text !== 'Next') continue;
            const rect = el.getBoundingClientRect();
            if (rect.width < 50 || rect.height < 20) continue;
            if (rect.bottom > bestBottom) {
                bestBottom = rect.bottom;
                best = el;
            }
        }

        if (best) {
            best.scrollIntoView({block: 'center'});
            best.click();
            return true;
        }
        return false;
        """
    )
    if clicked:
        print("✅ 已点击 Basic info 页面 Next 按钮")
        return True

    click_any_target_text(driver, ["Next"], timeout=5)
    print("✅ 已通过 fallback 点击 Next 按钮")
    return True


def _h5_get_reference_section_js():
    return """
        function collectFullNameRows() {
            const hits = [];
            const seen = new Set();
            for (const el of document.querySelectorAll('label, div, span, p')) {
                const t = (el.innerText || '').trim();
                if (!t.includes('Full Name')) continue;
                if (t.includes('Primary Reference') || t.includes('Secondary Reference')) continue;
                if (t.length > 100) continue;
                let node = el;
                for (let i = 0; i < 12; i++) {
                    if (!node) break;
                    const ct = (node.innerText || '').trim();
                    const r = node.getBoundingClientRect();
                    if (!ct.includes('Full Name')) {
                        node = node.parentElement;
                        continue;
                    }
                    if (ct.includes('Primary Reference') || ct.includes('Secondary Reference')) {
                        node = node.parentElement;
                        continue;
                    }
                    if (r.height < 28 || r.height > 180 || r.width < 60) {
                        node = node.parentElement;
                        continue;
                    }
                    const key = Math.round(r.top) + '|' + Math.round(r.left);
                    if (seen.has(key)) break;
                    seen.add(key);
                    hits.push({node: node, top: r.top, text: ct,
                        right: r.right, left: r.left, width: r.width, height: r.height});
                    break;
                }
            }
            hits.sort((a, b) => a.top - b.top);
            return hits;
        }

        function getFullNameRowBySection(sectionTitle) {
            const idx = sectionTitle === 'Secondary Reference' ? 1 : 0;
            const rows = collectFullNameRows();
            return rows[idx] || null;
        }

        function collectRelationshipRows() {
            const hits = [];
            const seen = new Set();
            for (const el of document.querySelectorAll('label, div, span, p')) {
                const t = (el.innerText || '').trim();
                if (!t.includes('Relationship')) continue;
                if (t.includes('Relationship with you')) continue;
                if (t.length > 120) continue;
                let node = el;
                for (let i = 0; i < 12; i++) {
                    if (!node) break;
                    const ct = (node.innerText || '').trim();
                    const r = node.getBoundingClientRect();
                    if (!ct.includes('Relationship')) {
                        node = node.parentElement;
                        continue;
                    }
                    if (r.height < 28 || r.height > 320 || r.width < 60) {
                        node = node.parentElement;
                        continue;
                    }
                    const key = Math.round(r.top) + '|' + Math.round(r.left);
                    if (seen.has(key)) break;
                    seen.add(key);
                    let bestNode = node;
                    let bestText = ct;
                    const lines = ct.split('\\n').map(s => s.trim()).filter(Boolean);
                    const onlyLabel = lines.length <= 1
                        || (lines.length === 2 && lines.every(l => l.toLowerCase() === 'relationship'));
                    if (onlyLabel) {
                        const p = node.parentElement;
                        if (p) {
                            const pt = (p.innerText || '').trim();
                            const pr = p.getBoundingClientRect();
                            if (pt.includes('Relationship') && pr.height <= 360 && pr.width >= 60) {
                                bestNode = p;
                                bestText = pt;
                            }
                        }
                    }
                    hits.push({node: bestNode, top: r.top, text: bestText});
                    break;
                }
            }
            hits.sort((a, b) => a.top - b.top);
            return hits;
        }

        function getRelationshipRowBySection(sectionTitle) {
            const idx = sectionTitle === 'Secondary Reference' ? 1 : 0;
            const rows = collectRelationshipRows();
            return rows[idx] || null;
        }

        function getReferenceSection(sectionTitle) {
            let best = null;
            let bestLen = Infinity;
            for (const el of document.querySelectorAll('h1,h2,h3,h4,div,section,p,span')) {
                const t = (el.innerText || '').trim();
                if (t !== sectionTitle && !t.startsWith(sectionTitle + '\\n')) continue;
                let node = el;
                for (let i = 0; i < 15; i++) {
                    if (!node) break;
                    const ct = (node.innerText || '').trim();
                    if (!ct.includes(sectionTitle)) {
                        node = node.parentElement;
                        continue;
                    }
                    if (!ct.includes('Relationship') || !ct.includes('Full Name')) {
                        node = node.parentElement;
                        continue;
                    }
                    if (sectionTitle === 'Primary Reference' && ct.includes('Secondary Reference')) {
                        node = node.parentElement;
                        continue;
                    }
                    if (sectionTitle === 'Secondary Reference' && !ct.includes('Secondary Reference')) {
                        node = node.parentElement;
                        continue;
                    }
                    if (ct.length < bestLen) {
                        bestLen = ct.length;
                        best = node;
                    }
                    break;
                }
            }
            return best;
        }

        function getFieldRowInSection(sectionTitle, labelKeyword) {
            const section = getReferenceSection(sectionTitle);
            if (!section) return getNthFieldRowOnPage(labelKeyword, sectionTitle === 'Secondary Reference' ? 1 : 0);

            for (const el of section.querySelectorAll('label, div, span, p')) {
                const t = (el.innerText || '').trim();
                if (!t.includes(labelKeyword)) continue;
                if (labelKeyword === 'Relationship' && !t.includes('Relationship')) continue;
                if (labelKeyword === 'Full Name' && !t.includes('Full Name')) continue;
                if (labelKeyword === 'Mobile' && !t.includes('Mobile')) continue;
                if (t.length > labelKeyword.length + 80) continue;
                let node = el;
                for (let i = 0; i < 10; i++) {
                    if (!node) break;
                    const ct = (node.innerText || '').trim();
                    const r = node.getBoundingClientRect();
                    if (!ct.includes(labelKeyword)) {
                        node = node.parentElement;
                        continue;
                    }
                    if (r.height < 30 || r.height > 280 || r.width < 80) {
                        node = node.parentElement;
                        continue;
                    }
                    return node;
                }
            }
            return getNthFieldRowOnPage(labelKeyword, sectionTitle === 'Secondary Reference' ? 1 : 0);
        }

        function getNthFieldRowOnPage(labelKeyword, index) {
            const hits = [];
            for (const el of document.querySelectorAll('label, div, span, p')) {
                const t = (el.innerText || '').trim();
                if (!t.includes(labelKeyword)) continue;
                if (labelKeyword === 'Relationship' && !t.includes('Relationship')) continue;
                if (labelKeyword === 'Full Name' && !t.includes('Full Name')) continue;
                if (labelKeyword === 'Mobile' && !t.includes('Mobile')) continue;
                if (t.length > labelKeyword.length + 80) continue;
                let node = el;
                for (let i = 0; i < 10; i++) {
                    if (!node) break;
                    const ct = (node.innerText || '').trim();
                    const r = node.getBoundingClientRect();
                    if (!ct.includes(labelKeyword)) {
                        node = node.parentElement;
                        continue;
                    }
                    if (r.height < 30 || r.height > 280 || r.width < 80) continue;
                    if (r.top < 0 || r.top > window.innerHeight) continue;
                    hits.push(node);
                    break;
                }
            }
            hits.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
            return hits[index] || null;
        }

        function clickNthPlaceholderInSection(sectionTitle, placeholder) {
            const section = getReferenceSection(sectionTitle);
            const scope = section || document.body;
            const hits = [];
            for (const el of scope.querySelectorAll('div, span, p, label, input, textarea')) {
                const t = (el.innerText || el.placeholder || el.getAttribute('placeholder') || '').trim();
                if (!t.includes(placeholder) && t !== placeholder) continue;
                const r = el.getBoundingClientRect();
                if (r.height < 5 || r.width < 5 || r.top < 0 || r.top > window.innerHeight) continue;
                hits.push(el);
            }
            hits.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
            const idx = sectionTitle === 'Secondary Reference' ? 1 : 0;
            const target = hits[idx] || hits[0];
            if (!target) return false;
            target.scrollIntoView({block: 'center', behavior: 'instant'});
            target.click();
            try { (target.closest('div') || target).click(); } catch (e) {}
            return true;
        }
    """


REFERENCE_RELATIONSHIP_OPTIONS = (
    "father/mother",
    "husband/wife",
    "son/daughter",
    "friend",
    "Uncle/Aunt",
)


def h5_section_shows_placeholder(driver, section_title, placeholder):
    """区块内是否仍显示某 placeholder（未填）"""
    return driver.execute_script(
        _h5_get_reference_section_js()
        + """
        const section = getReferenceSection(arguments[0]);
        if (!section) return true;
        return (section.innerText || '').includes(arguments[1]);
        """,
        section_title,
        placeholder,
    )


def h5_get_section_relationship_value(driver, section_title):
    """读取区块内 Relationship 已选值（按 Primary/Secondary 行序），未选则返回 None"""
    return driver.execute_script(
        _h5_get_reference_section_js()
        + """
        const sectionTitle = arguments[0];
        const known = arguments[1];
        const knownLower = known.map(s => s.toLowerCase());

        function pickFromText(text) {
            const t = (text || '').toLowerCase();
            if (!t) return null;
            const lines = (text || '').split('\\n').map(s => s.trim()).filter(Boolean);
            for (const line of lines) {
                const l = line.toLowerCase();
                if (l === 'relationship') continue;
                if (l.startsWith('select ')) continue;
                for (let i = 0; i < knownLower.length; i++) {
                    if (l === knownLower[i] || l.includes(knownLower[i])) return known[i];
                }
            }
            for (let i = 0; i < knownLower.length; i++) {
                if (t.includes(knownLower[i])) return known[i];
            }
            return null;
        }

        const row = getRelationshipRowBySection(sectionTitle);
        if (row) {
            const rowText = (row.text || '').toLowerCase();
            if (!rowText.includes('select relationship')) {
                const hit = pickFromText(row.text || '');
                if (hit) return hit;
            }
        }

        const section = getReferenceSection(sectionTitle);
        if (section) {
            const hit = pickFromText(section.innerText || '');
            if (hit) return hit;
        }
        return null;
        """,
        section_title,
        list(REFERENCE_RELATIONSHIP_OPTIONS),
    )


def h5_relationship_placeholder_gone(driver, section_title):
    """该区块 Relationship 行已不再显示 Select relationship"""
    return driver.execute_script(
        _h5_get_reference_section_js()
        + """
        const row = getRelationshipRowBySection(arguments[0]);
        if (!row) return false;
        const t = (row.text || '').toLowerCase();
        return !t.includes('select relationship');
        """,
        section_title,
    )


def h5_section_relationship_filled(driver, section_title, expected_value=None):
    """Relationship 已选：行内出现任意已知选项；传 expected_value 时额外校验是否匹配"""
    existing = h5_get_section_relationship_value(driver, section_title)
    if not existing:
        return False
    if expected_value:
        exp = expected_value.strip().lower()
        return existing.strip().lower() == exp or exp in existing.strip().lower()
    return True


def _h5_fullname_validation_js():
    return """
        function isValidContactName(line, knownRels) {
            const l = (line || '').trim();
            if (!l) return false;
            const lower = l.toLowerCase();
            const blocked = [
                'full name', 'mobile', 'relationship',
                'primary reference', 'secondary reference',
                'reference contacts', 'select relationship',
                'provide people', 'relationship with you',
            ];
            if (blocked.some(b => lower === b || lower.includes(b))) return false;
            if (lower.startsWith('select ')) return false;
            if (lower.includes('e.g.')) return false;
            if (lower.includes('avoid nicknames')) return false;
            if (knownRels.some(r => lower === r || lower.includes(r))) return false;
            if (/^[A-Za-z]\\s*$/.test(l)) return false;
            if (/^\\+?\\d{1,4}\\s*$/.test(l)) return false;
            if (/^[A-Za-z]\\+?\\d{0,4}\\s*$/.test(l)) return false;
            if (/^A\\d+$/.test(l)) return true;
            if (l.length >= 3 && /[A-Za-z]{2,}/.test(l) && !/reference/i.test(l)) return true;
            return false;
        }

        function isValidMobileText(text) {
            const raw = (text || '').trim();
            if (!raw || raw.toLowerCase().includes('e.g.')) return false;
            const digits = raw.replace(/\\s/g, '').replace(/\\D/g, '');
            return digits.length >= 6;
        }

        function fullNameRowStillEmpty(rowText, placeholder) {
            const t = (rowText || '').toLowerCase();
            const ph = (placeholder || '').toLowerCase();
            if (t.includes('e.g.') || t.includes('avoid nicknames')) return true;
            if (ph && t.includes(ph.slice(0, 14))) return true;
            return false;
        }

        function extractFullNameValue(row, placeholder, knownRels) {
            if (!row) return null;
            const rowText = row.text || row.innerText || '';
            if (fullNameRowStillEmpty(rowText, placeholder)) return null;
            const node = row.node || row;
            for (const inp of node.querySelectorAll('input, textarea')) {
                const v = (inp.value || '').trim();
                if (isValidContactName(v, knownRels)) return v;
            }
            const lines = rowText.trim().split('\\n').map(s => s.trim()).filter(Boolean);
            for (const line of lines) {
                if (isValidContactName(line, knownRels)) return line;
            }
            return null;
        }
    """


def h5_get_section_fullname_display(driver, section_title, placeholder):
    """读取 Full Name 行内已填姓名（用于跳过日志）"""
    return driver.execute_script(
        _h5_get_reference_section_js()
        + _h5_fullname_validation_js()
        + """
        const sectionTitle = arguments[0];
        const placeholder = arguments[1];
        const knownRels = arguments[2].map(s => s.toLowerCase());
        const row = getFullNameRowBySection(sectionTitle);
        return extractFullNameValue(row, placeholder, knownRels);
        """,
        section_title,
        placeholder,
        list(REFERENCE_RELATIONSHIP_OPTIONS),
    )


def h5_section_fullname_filled(driver, section_title, placeholder):
    """Full Name / Mobile 已填：行内无 placeholder 且有真实姓名或手机号"""
    return driver.execute_script(
        _h5_get_reference_section_js()
        + _h5_fullname_validation_js()
        + """
        const sectionTitle = arguments[0];
        const placeholder = arguments[1];
        const knownRels = arguments[2].map(s => s.toLowerCase());

        const nameRow = getFullNameRowBySection(sectionTitle);
        if (extractFullNameValue(nameRow, placeholder, knownRels)) return true;

        const mobileRow = getFieldRowInSection(sectionTitle, 'Mobile');
        if (mobileRow) {
            const mt = (mobileRow.innerText || '').toLowerCase();
            if (mt.includes('e.g.')) return false;
            for (const inp of mobileRow.querySelectorAll('input, textarea')) {
                if (isValidMobileText(inp.value || '')) return true;
            }
            if (isValidMobileText(mobileRow.innerText || '')) return true;
        }
        return false;
        """,
        section_title,
        placeholder,
        list(REFERENCE_RELATIONSHIP_OPTIONS),
    )


def h5_reference_relationship_empty(driver, section_title):
    return h5_section_shows_placeholder(driver, section_title, "Select relationship")


def h5_reference_fullname_empty(driver, section_title, placeholder):
    return not h5_section_fullname_filled(driver, section_title, placeholder)


def ensure_emergency_contacts_page(driver, timeout=15):
    """通讯录选完人后回到 Reference Contacts 页"""
    try:
        switch_to_real_webview(driver, keyword="emergencyContacts", timeout=timeout)
    except Exception:
        try:
            switch_to_real_webview(driver, timeout=timeout)
        except Exception:
            pass
    wait_for_h5_text(driver, "Reference Contacts", timeout=10)
    time.sleep(0.8)


def h5_select_has_value_in_section(driver, section_title, label, expected_value):
    """参照 h5_select_has_value：仅在区块内 Relationship 字段行出现 expected 才算已选"""
    return driver.execute_script(
        _h5_get_reference_section_js()
        + """
        const sectionTitle = arguments[0];
        const label = arguments[1];
        const expected = (arguments[2] || '').trim().toLowerCase();
        if (!expected) return false;

        function norm(s) { return (s || '').trim().toLowerCase(); }
        function matchValue(line, exp) {
            const l = norm(line);
            const e = norm(exp);
            return l === e || l.includes(e) || e.includes(l);
        }

        const row = getFieldRowInSection(sectionTitle, label);
        if (!row) return false;

        const rowText = (row.innerText || '').trim();
        if (norm(rowText).includes('select relationship')) return false;

        const lines = rowText.split('\\n').map(s => s.trim()).filter(Boolean);
        for (const line of lines) {
            if (norm(line).includes(norm(label))) continue;
            if (line.startsWith('Select ')) continue;
            if (matchValue(line, expected)) return true;
        }

        for (const inp of row.querySelectorAll('input, textarea')) {
            const v = (inp.value || '').trim();
            if (v && matchValue(v, expected)) return true;
        }
        return false;
        """,
        section_title,
        label,
        expected_value,
    )


def h5_reference_section_field_filled(driver, section_title, label, placeholder_hint):
    """判断 Reference Contacts 某区块内字段是否已填"""
    if label == "Relationship":
        return bool(h5_get_section_relationship_value(driver, section_title))
    if label == "Full Name":
        return h5_section_fullname_filled(driver, section_title, placeholder_hint)

    known_relationships = list(REFERENCE_RELATIONSHIP_OPTIONS)
    return driver.execute_script(
        _h5_get_reference_section_js()
        + """
        const sectionTitle = arguments[0];
        const label = arguments[1];
        const ph = (arguments[2] || '').trim().toLowerCase();
        const knownRels = arguments[3].map(s => s.toLowerCase());
        const row = getFieldRowInSection(sectionTitle, label);
        if (!row) {
            const section = getReferenceSection(sectionTitle);
            if (!section) return false;
            if (label === 'Relationship') {
                const st = (section.innerText || '').toLowerCase();
                if (st.includes('select relationship')) return false;
                return knownRels.some(r => st.includes(r));
            }
            return false;
        }
        const text = (row.innerText || '').trim().toLowerCase();
        if (label === 'Relationship') {
            if (text.includes('select relationship')) return false;
            if (knownRels.some(r => text.includes(r))) return true;
            const lines = (row.innerText || '').trim().split('\\n').map(s => s.trim()).filter(Boolean);
            for (const line of lines) {
                const l = line.toLowerCase();
                if (l === 'relationship') continue;
                if (l.startsWith('select ')) continue;
                if (line.length >= 3) return true;
            }
            return false;
        }
        if (ph && text.includes(ph)) return false;
        if (label === 'Full Name' && text.includes('e.g. rahul')) return false;
        if (label === 'Mobile' && text.includes('e.g. 98115')) return false;
        const lines = (row.innerText || '').trim().split('\\n').map(s => s.trim()).filter(Boolean);
        for (const line of lines) {
            const l = line.toLowerCase();
            if (l === label.toLowerCase()) continue;
            if (l.startsWith('select ')) continue;
            if (l.includes('e.g.')) continue;
            if (label === 'Full Name') {
                if (l === 'full name' || l === 'mobile') continue;
                if (line.length >= 2) return true;
            }
            if (label === 'Mobile') {
                if (/\\d{6,}/.test(line)) return true;
                continue;
            }
            if (line.length >= 2) return true;
        }
        return false;
        """,
        section_title,
        label,
        placeholder_hint,
        known_relationships,
    )


def h5_open_select_dropdown_in_section(driver, section_title, label, placeholder):
    """
    参照 h5_open_select_dropdown：在 Primary/Secondary Reference 区块内点击 placeholder 打开底部弹窗
    """
    h5_hide_keyboard(driver)
    h5_scroll_to_label(driver, section_title)
    time.sleep(0.3)

    # 策略1：区块内字段行点击（与 basic info 一致，优先点 Relationship 行）
    opened = driver.execute_script(
        _h5_get_reference_section_js()
        + """
        const sectionTitle = arguments[0];
        const label = arguments[1];
        const placeholder = arguments[2];
        const section = getReferenceSection(sectionTitle);
        if (!section) return false;

        const row = getFieldRowInSection(sectionTitle, label);
        if (row) {
            row.scrollIntoView({block: 'center', behavior: 'instant'});
            for (const inp of row.querySelectorAll('input, textarea')) {
                const attr = (inp.placeholder || inp.getAttribute('placeholder') || '').trim();
                if (attr.includes(placeholder.replace(/^Select\\s+/i, '')) || attr === placeholder) {
                    inp.click();
                    (inp.closest('div') || inp).click();
                    return true;
                }
            }
            for (const el of row.querySelectorAll('div, span, p, label')) {
                const t = (el.innerText || el.placeholder || el.getAttribute('placeholder') || '').trim();
                if (!t) continue;
                if (!t.includes(placeholder) && t !== placeholder) continue;
                el.click();
                try { (el.closest('div') || el).click(); } catch (e) {}
                return true;
            }
            row.click();
            return true;
        }

        for (const el of section.querySelectorAll('div, span, p, label, input, textarea')) {
            const t = (el.innerText || el.placeholder || el.getAttribute('placeholder') || '').trim();
            if (!t) continue;
            if (!t.includes(placeholder) && t !== placeholder) continue;
            const r = el.getBoundingClientRect();
            if (r.height < 8 || r.width < 8) continue;
            el.scrollIntoView({block: 'center', behavior: 'instant'});
            el.click();
            try { (el.closest('div') || el).click(); } catch (e) {}
            return true;
        }
        return false;
        """,
        section_title,
        label,
        placeholder,
    )
    if opened:
        time.sleep(0.6)
        print(f"已打开选择框: {section_title} -> {label} ({placeholder})")
        return True

    # 策略2：坐标点击 placeholder 行（Vue 组件）
    tap = driver.execute_script(
        _h5_get_reference_section_js()
        + """
        const row = getFieldRowInSection(arguments[0], arguments[1]);
        if (!row) return null;
        row.scrollIntoView({block: 'center', behavior: 'instant'});
        const r = row.getBoundingClientRect();
        return {x: r.left + r.width * 0.55, y: r.top + r.height * 0.62};
        """,
        section_title,
        label,
    )
    if tap:
        h5_tap_at(driver, tap["x"], tap["y"])
        time.sleep(0.6)
        print(f"已打开选择框(坐标): {section_title} -> {label}")
        return True

    # 策略3：按 Primary/Secondary 顺序点第 N 个 Select relationship
    opened_nth = driver.execute_script(
        _h5_get_reference_section_js()
        + """
        return clickNthPlaceholderInSection(arguments[0], arguments[1]);
        """,
        section_title,
        placeholder,
    )
    if opened_nth:
        time.sleep(0.6)
        print(f"已打开选择框(顺序): {section_title} -> {label}")
        return True

    print(f"⚠️ 无法打开选择框: {section_title} -> {label}（placeholder: {placeholder}）")
    return False


def h5_open_reference_section_field(driver, section_title, label, placeholder):
    """点击 Reference Contacts 指定区块内的字段行（Full Name 点右侧箭头区域）"""
    h5_hide_keyboard(driver)
    h5_scroll_to_label(driver, section_title)
    time.sleep(0.3)

    tap_info = driver.execute_script(
        _h5_get_reference_section_js()
        + """
        const sectionTitle = arguments[0];
        const label = arguments[1];
        const placeholder = arguments[2];
        const row = getFieldRowInSection(sectionTitle, label);
        if (!row) return null;
        row.scrollIntoView({block: 'center', behavior: 'instant'});

        const r = row.getBoundingClientRect();
        const info = {
            x: r.right - Math.max(28, r.width * 0.08),
            y: r.top + r.height / 2,
            cx: r.left + r.width / 2,
            cy: r.top + r.height / 2,
        };

        if (placeholder) {
            for (const el of row.querySelectorAll('*')) {
                const t = (el.innerText || '').trim();
                if (t.includes(placeholder) || t === placeholder) {
                    const er = el.getBoundingClientRect();
                    info.x = er.left + er.width / 2;
                    info.y = er.top + er.height / 2;
                    el.click();
                    info.clicked = 'placeholder';
                    return info;
                }
            }
        }

        row.click();
        info.clicked = 'row';
        return info;
        """,
        section_title,
        label,
        placeholder,
    )

    clicked = False
    if tap_info:
        print(f"已打开字段: {section_title} -> {label} ({tap_info.get('clicked', 'js')})")
        clicked = True
        if label == "Full Name":
            time.sleep(0.2)
            h5_tap_at(driver, tap_info["x"], tap_info["y"])
            time.sleep(0.2)
            h5_tap_at(driver, tap_info["cx"], tap_info["cy"])

    if not clicked:
        try:
            h5_click_text_and_parents(driver, placeholder, timeout=3)
            print(f"已打开字段(fallback): {section_title} -> {label}")
            clicked = True
        except Exception:
            print(f"⚠️ 无法打开字段: {section_title} -> {label}")
            return False

    if label == "Full Name":
        time.sleep(1.2)
    return clicked


def h5_click_first_relationship_option(driver, modal_title="Relationship with you"):
    """Relationship 弹窗：只在底部 sheet 内选第一项（father/mother）"""
    time.sleep(0.8)

    if not h5_modal_is_open(driver, modal_title):
        print("⚠️ Relationship 弹窗未检测到，尝试继续点选...")

    for opt in REFERENCE_RELATIONSHIP_OPTIONS:
        if h5_click_by_exact_text(driver, opt, timeout=2, in_bottom_sheet=True):
            time.sleep(0.6)
            print(f"✅ Relationship 已选: {opt}")
            return opt

    picked = driver.execute_script(
        """
        const modalTitle = arguments[0];
        const known = arguments[1];
        const skip = new Set([
            modalTitle, 'Relationship with you', 'Relationship',
            'Primary Reference', 'Secondary Reference',
            'Full Name', 'Mobile', 'Select relationship',
        ]);

        let titleBottom = window.innerHeight * 0.32;
        for (const el of document.querySelectorAll('div, span, p, h1, h2, h3')) {
            if ((el.innerText || '').trim() === modalTitle) {
                titleBottom = el.getBoundingClientRect().bottom;
                break;
            }
        }

        for (const optText of known) {
            for (const el of document.querySelectorAll('div, span, li, p, label')) {
                const t = (el.innerText || '').trim();
                if (t !== optText) continue;
                const r = el.getBoundingClientRect();
                if (r.top < titleBottom - 8) continue;
                if (r.top < window.innerHeight * 0.25) continue;
                if (r.height < 28 || r.height > 110) continue;
                if (skip.has(t)) continue;

                let row = el;
                for (let i = 0; i < 8; i++) {
                    const p = row.parentElement;
                    if (!p) break;
                    const pr = p.getBoundingClientRect();
                    if (pr.height >= 40 && pr.height <= 115) row = p;
                }
                row.click();
                return t;
            }
        }
        return null;
        """,
        modal_title,
        list(REFERENCE_RELATIONSHIP_OPTIONS),
    )
    if picked:
        time.sleep(0.6)
        print(f"✅ Relationship 已选第一项: {picked}")
        return picked

    print("⚠️ Relationship 选项未能点击")
    return None


def _get_webview_context(driver):
    for ctx in driver.contexts:
        if "WEBVIEW" in ctx:
            return ctx
    return None


def _native_in_contact_picker(driver, timeout=5):
    """是否已进入原生「Select contacts」通讯录页（必须在 NATIVE_APP 上下文检测）"""
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            driver.switch_to.context("NATIVE_APP")
            for title in ("Select contacts", "Select contact"):
                for el in driver.find_elements(
                    AppiumBy.XPATH, f"//*[contains(@text,'{title}')]"
                ):
                    if el.is_displayed():
                        return True
            page = driver.page_source or ""
            if "Select contacts" in page or "Select contact" in page:
                return True
        except Exception:
            pass
        time.sleep(0.35)
    return False


def h5_open_fullname_contact_picker(driver, section_title, placeholder, max_attempts=4):
    """WebView 点击 Full Name 行右侧，等待原生通讯录打开"""
    webview_ctx = _get_webview_context(driver)
    h5_hide_keyboard(driver)
    h5_scroll_to_label(driver, section_title)
    time.sleep(0.4)

    for attempt in range(max_attempts):
        if webview_ctx and webview_ctx in driver.contexts:
            try:
                driver.switch_to.context(webview_ctx)
            except Exception:
                pass

        tap_info = driver.execute_script(
            _h5_get_reference_section_js()
            + """
            const row = getFullNameRowBySection(arguments[0]);
            if (!row) return null;
            row.node.scrollIntoView({block: 'center', behavior: 'instant'});
            const r = row.node.getBoundingClientRect();
            return {
                x: r.right - Math.max(36, r.width * 0.06),
                y: r.top + r.height / 2,
                cx: r.left + r.width * 0.72,
                cy: r.top + r.height / 2,
            };
            """,
            section_title,
        )

        if tap_info:
            h5_tap_at(driver, tap_info["x"], tap_info["y"])
            time.sleep(0.35)
            h5_tap_at(driver, tap_info["cx"], tap_info["cy"])
            print(
                f"已点击 Full Name 行: {section_title} "
                f"(尝试 {attempt + 1}/{max_attempts})"
            )
        else:
            if not h5_open_reference_section_field(
                driver, section_title, "Full Name", placeholder
            ):
                time.sleep(0.5)
                continue

        if _native_in_contact_picker(driver, timeout=5):
            print(f"✅ 原生通讯录已打开: {section_title}")
            return True

        time.sleep(0.6)

    print(f"⚠️ 未能打开原生通讯录: {section_title}")
    return False


def _native_collect_contact_items(driver):
    """收集通讯录列表中可点的联系人行（跳过搜索栏、字母索引）"""
    items = []
    preferred_names = ("A1", "A2", "A3", "A5")

    for name in preferred_names:
        try:
            for el in driver.find_elements(AppiumBy.XPATH, f"//*[@text='{name}']"):
                if not el.is_displayed():
                    continue
                row = el
                for _ in range(4):
                    try:
                        parent = row.find_element(AppiumBy.XPATH, "..")
                        if parent.is_displayed():
                            row = parent
                    except Exception:
                        break
                txt = (row.text or name).strip()
                items.append((row, txt))
        except Exception:
            pass

    if items:
        return items

    for rv_class in (
        "androidx.recyclerview.widget.RecyclerView",
        "android.widget.ListView",
    ):
        try:
            for lst in driver.find_elements(AppiumBy.CLASS_NAME, rv_class):
                if not lst.is_displayed():
                    continue
                for item in lst.find_elements(AppiumBy.XPATH, "./*"):
                    try:
                        if not item.is_displayed():
                            continue
                        txt = (item.text or "").strip()
                        if not txt:
                            continue
                        if "Search" in txt or "Select contact" in txt:
                            continue
                        if len(txt) == 1 and txt.isalpha():
                            continue
                        digits = "".join(c for c in txt.replace(" ", "") if c.isdigit())
                        if len(digits) < 6:
                            continue
                        items.append((item, txt))
                    except Exception:
                        continue
        except Exception:
            pass
    return items


def _native_click_contact_by_name(driver, name):
    """原生通讯录按姓名精确点击（支持滚动查找）"""
    handle_permission_popup(driver, timeout=2)
    try:
        uiauto = (
            f'new UiScrollable(new UiSelector().scrollable(true).instance(0))'
            f'.scrollIntoView(new UiSelector().text("{name}"))'
        )
        el = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, uiauto)
        if el.is_displayed():
            row = el
            for _ in range(3):
                try:
                    parent = row.find_element(AppiumBy.XPATH, "..")
                    if parent.is_displayed():
                        row = parent
                except Exception:
                    break
            row.click()
            print(f"✅ 原生通讯录：已选择 {name}")
            return True
    except Exception:
        pass

    try:
        for el in driver.find_elements(AppiumBy.XPATH, f"//*[@text='{name}']"):
            if not el.is_displayed():
                continue
            row = el
            for _ in range(4):
                try:
                    parent = row.find_element(AppiumBy.XPATH, "..")
                    if parent.is_displayed():
                        row = parent
                except Exception:
                    break
            row.click()
            print(f"✅ 原生通讯录：已选择 {name} ({row.text or name})")
            return True
    except Exception:
        pass
    return False


def _native_try_click_contact_row(driver, index=0):
    """在原生通讯录点击第 index 个联系人（0=A1，1=A2…）"""
    handle_permission_popup(driver, timeout=3)

    preferred_names = ("A1", "A2", "A3", "A5")
    if index < len(preferred_names):
        name = preferred_names[index]
        if _native_click_contact_by_name(driver, name):
            return True

    items = _native_collect_contact_items(driver)
    if items:
        idx = min(index, len(items) - 1)
        el, txt = items[idx]
        el.click()
        print(f"✅ 原生通讯录：已选择第 {idx + 1} 个联系人 {txt or '(列表项)'}")
        return True

    if not _native_in_contact_picker(driver, timeout=1):
        print("⚠️ 未进入原生通讯录页，跳过 UiScrollable/坐标兜底")
        return False

    uiauto = (
        f'new UiScrollable(new UiSelector().scrollable(true).instance(0))'
        f'.getChildByInstance(new UiSelector().clickable(true), {index})'
    )
    try:
        el = driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, uiauto)
        if el.is_displayed():
            name = (el.text or "").strip()
            el.click()
            print(f"✅ 原生通讯录：UiScrollable 第 {index + 1} 个 {name or ''}")
            return True
    except Exception:
        pass

    try:
        size = driver.get_window_size()
        y = int(size["height"] * (0.22 + index * 0.09))
        x = int(size["width"] * 0.45)
        driver.tap([(x, y)], 250)
        print(f"✅ 原生通讯录：坐标点击第 {index + 1} 个 ({x}, {y})")
        return True
    except Exception:
        pass

    return False


def native_pick_contact_by_index(driver, index=0, timeout=20):
    """原生通讯录：选第 index 个联系人（Primary=0→A1，Secondary=1→A2）"""
    webview_context = _get_webview_context(driver)
    preferred_names = ("A1", "A2", "A3", "A5")
    target_name = preferred_names[index] if index < len(preferred_names) else None

    picked = False
    end_time = time.time() + timeout

    try:
        driver.switch_to.context("NATIVE_APP")
        while time.time() < end_time and not picked:
            if not _native_in_contact_picker(driver, timeout=1):
                time.sleep(0.4)
                continue

            if target_name and _native_click_contact_by_name(driver, target_name):
                picked = True
                time.sleep(1.2)
                break

            picked = _native_try_click_contact_row(driver, index=index)
            if picked:
                time.sleep(1.2)
                break

            time.sleep(0.45)

        if not picked:
            print(f"⚠️ 原生通讯录：未能选择第 {index + 1} 个联系人")
            try:
                driver.save_screenshot(f"native_contact_picker_fail_{index}.png")
            except Exception:
                pass
        return picked

    finally:
        time.sleep(0.5)
        try:
            if webview_context and webview_context in driver.contexts:
                driver.switch_to.context(webview_context)
        except Exception:
            pass


def native_pick_first_contact(driver, timeout=20):
    """兼容旧调用：选第一个联系人"""
    return native_pick_contact_by_index(driver, index=0, timeout=timeout)


def h5_click_enabled_next(driver, timeout=30, max_swipes=12):
    """Reference Contacts：等 Next 可点后点击（支持下滑查找）"""
    end_time = time.time() + timeout
    swipe_count = 0

    while time.time() < end_time:
        clicked = driver.execute_script(
            """
            let best = null;
            let bestBottom = -1;
            for (const el of document.querySelectorAll('button, a, div, span, p')) {
                const text = (el.innerText || '').trim();
                if (text !== 'Next') continue;
                const rect = el.getBoundingClientRect();
                if (rect.width < 80 || rect.height < 28) continue;
                const cls = ((el.className || '') + ' ' + (el.getAttribute('class') || '')).toLowerCase();
                if (cls.includes('disabled') || cls.includes('disable') || cls.includes('inactive')) continue;
                const op = parseFloat(window.getComputedStyle(el).opacity || '1');
                if (op < 0.55) continue;
                const pe = window.getComputedStyle(el).pointerEvents;
                if (pe === 'none') continue;
                if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                const bg = window.getComputedStyle(el).backgroundColor || '';
                if (bg.includes('200') && bg.includes('200') && bg.includes('200')) continue;
                if (rect.bottom > bestBottom) {
                    bestBottom = rect.bottom;
                    best = el;
                }
            }
            if (best) {
                best.scrollIntoView({block: 'center', behavior: 'instant'});
                best.click();
                return true;
            }
            return false;
            """
        )
        if clicked:
            print("✅ 已点击 Reference Contacts 页面 Next 按钮")
            return True

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        if swipe_count < max_swipes:
            swipe_up_h5(driver)
            swipe_count += 1
        time.sleep(0.6)

    raise TimeoutException("Reference Contacts 页面 Next 按钮不可用或未找到（请确认四个字段均已填写）")


def fill_reference_contacts_form(driver, max_swipes=20):
    """
    填写 Reference Contacts（紧急联系人）
    流程对齐 fill_basic_info_form：先 Relationship 下拉，再 Full Name 通讯录，最后 Next
    """
    print("=== 开始填写 Reference Contacts 表单 ===")

    wait_for_h5_text(driver, "Reference Contacts", timeout=20)
    try:
        switch_to_real_webview(driver, timeout=10)
    except Exception:
        pass

    driver.execute_script("window.scrollTo(0, 0);")
    wait_for_h5_text(driver, "Select relationship", timeout=10)
    time.sleep(1.0)

    form_fields = [
        {
            "section": "Primary Reference",
            "type": "select",
            "label": "Relationship",
            "placeholder": "Select relationship",
            "value": "father/mother",
            "modal": "Relationship with you",
        },
        {
            "section": "Primary Reference",
            "type": "contact",
            "label": "Full Name",
            "placeholder": "e.g. Rahul Kumar Sharma (avoid nicknames)",
            "mobile_ph": "e.g. 98115 43210",
            "contact_index": 0,
        },
        {
            "section": "Secondary Reference",
            "type": "select",
            "label": "Relationship",
            "placeholder": "Select relationship",
            "value": "father/mother",
            "modal": "Relationship with you",
        },
        {
            "section": "Secondary Reference",
            "type": "contact",
            "label": "Full Name",
            "placeholder": "e.g. Rahul Kumar Sharma (avoid nicknames)",
            "mobile_ph": "e.g. 98115 43210",
            "contact_index": 1,
        },
    ]

    done_keys = set()

    def field_key(field):
        return f"{field['section']}::{field['type']}::{field['label']}"

    def process_select(field):
        """与 fill_basic_info_form.process_select 相同模式"""
        key = field_key(field)
        if key in done_keys:
            return False

        section = field["section"]
        label = field["label"]
        placeholder = field["placeholder"]
        option = field["value"]
        modal = field.get("modal", label)

        h5_hide_keyboard(driver)
        h5_scroll_to_label(driver, section)

        existing = h5_get_section_relationship_value(driver, section)
        if existing:
            done_keys.add(key)
            print(f"⏭️ 跳过 {section} {label}（已有: {existing}）")
            return True

        if not h5_open_select_dropdown_in_section(driver, section, label, placeholder):
            return False

        time.sleep(1.0)
        picked = h5_click_select_option(driver, option, modal_title=modal)

        if picked:
            h5_dismiss_modal_if_open(driver)
            for attempt in range(5):
                time.sleep(0.5 if attempt else 0.8)
                existing = h5_get_section_relationship_value(driver, section)
                if existing:
                    done_keys.add(key)
                    print(f"✅ {section} {label} 已确认选中: {existing}")
                    return True
                if h5_relationship_placeholder_gone(driver, section):
                    done_keys.add(key)
                    print(f"✅ {section} {label} 已确认选中: {picked}")
                    return True
                if not h5_modal_is_open(driver, modal):
                    done_keys.add(key)
                    print(f"✅ {section} {label} 已确认选中: {picked}（弹窗已关闭）")
                    return True
            print(f"⚠️ {section} {label} 点击后校验未读到 {option}，稍后重试")
            return False

        h5_dismiss_modal_if_open(driver)
        print(f"⚠️ {section} {label} 选择未生效，稍后重试")
        return False

    def process_contact(field):
        """Full Name：点开原生通讯录，Primary 选第1个、Secondary 选第2个联系人"""
        key = field_key(field)
        if key in done_keys:
            return False

        section = field["section"]
        label = field["label"]
        placeholder = field["placeholder"]
        contact_index = field.get("contact_index", 0)

        ensure_emergency_contacts_page(driver)
        h5_scroll_to_label(driver, section)

        if h5_section_fullname_filled(driver, section, placeholder):
            done_keys.add(key)
            display = h5_get_section_fullname_display(driver, section, placeholder)
            print(f"⏭️ 跳过 {section} Full Name / Mobile（已有: {display or '已填'}）")
            return True

        if not h5_open_fullname_contact_picker(driver, section, placeholder):
            if h5_section_fullname_filled(driver, section, placeholder):
                done_keys.add(key)
                display = h5_get_section_fullname_display(driver, section, placeholder)
                print(f"⏭️ 跳过 {section} Full Name / Mobile（已有: {display or '已填'}）")
                return True
            print(f"⚠️ {section} 未打开原生通讯录，稍后重试")
            return False

        if not native_pick_contact_by_index(driver, index=contact_index, timeout=25):
            return False

        ensure_emergency_contacts_page(driver)
        time.sleep(1.0)

        if h5_section_fullname_filled(driver, section, placeholder):
            done_keys.add(key)
            print(f"✅ {section} 已选择第 {contact_index + 1} 个联系人")
            return True

        print(f"⚠️ {section} 通讯录选择后未回填，稍后重试")
        return False

    select_fields = [f for f in form_fields if f["type"] == "select"]
    contact_fields = [f for f in form_fields if f["type"] == "contact"]
    n_select = len(select_fields)
    n_contact = len(contact_fields)

    # === 预扫描：已有值的字段直接标记完成，避免重复点击 ===
    print("--- 预扫描已填字段 ---")
    for field in form_fields:
        key = field_key(field)
        section = field["section"]
        if field["type"] == "select":
            existing = h5_get_section_relationship_value(driver, section)
            if existing:
                done_keys.add(key)
                print(f"⏭️ 跳过 {section} Relationship（已有: {existing}）")
        elif field["type"] == "contact":
            placeholder = field["placeholder"]
            if h5_section_fullname_filled(driver, section, placeholder):
                done_keys.add(key)
                display = h5_get_section_fullname_display(driver, section, placeholder)
                print(f"⏭️ 跳过 {section} Full Name / Mobile（已有: {display or '已填'}）")

    if len(done_keys) == len(form_fields):
        print("⏭️ 全部字段已有值，跳过填写直接提交")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.8)
        h5_click_enabled_next(driver, timeout=30, max_swipes=12)
        time.sleep(2)
        print("✅ Reference Contacts 表单填写并提交完成")
        return

    # === 阶段1：Relationship 下拉（同 basic info 阶段1）===
    print("--- 阶段1：Relationship 下拉 ---")
    h5_hide_keyboard(driver)
    swipe_count = 0
    while len([f for f in select_fields if field_key(f) in done_keys]) < n_select and swipe_count <= max_swipes:
        progressed = False
        for field in select_fields:
            if process_select(field):
                progressed = True

        done_n = len([f for f in select_fields if field_key(f) in done_keys])
        print(f"Relationship 进度: {done_n}/{n_select}")

        if not progressed:
            swipe_up_h5(driver)
            swipe_count += 1
            if swipe_count % 4 == 0:
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.5)
        else:
            swipe_count = 0

    # === 阶段2：Full Name 通讯录 ===
    print("--- 阶段2：Full Name 通讯录 ---")
    h5_hide_keyboard(driver)
    swipe_count = 0
    while len([f for f in contact_fields if field_key(f) in done_keys]) < n_contact and swipe_count <= max_swipes:
        progressed = False
        for field in contact_fields:
            rel_key = field_key({**field, "type": "select", "label": "Relationship"})
            if rel_key not in done_keys:
                continue
            if process_contact(field):
                progressed = True

        done_n = len([f for f in contact_fields if field_key(f) in done_keys])
        print(f"通讯录 进度: {done_n}/{n_contact}")

        if not progressed:
            swipe_up_h5(driver)
            swipe_count += 1
        else:
            swipe_count = 0

    all_ok = (
        len([f for f in select_fields if field_key(f) in done_keys]) == n_select
        and len([f for f in contact_fields if field_key(f) in done_keys]) == n_contact
    )

    if not all_ok:
        driver.save_screenshot("reference_contacts_incomplete.png")
        print("⚠️ Reference Contacts 未全部填写完成，请检查 reference_contacts_incomplete.png")
        raise TimeoutException(
            "Reference Contacts 表单未填完：Relationship 或 Full Name 仍有空项"
        )

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(0.8)
    driver.save_screenshot("reference_contacts_before_next.png")

    h5_click_enabled_next(driver, timeout=30, max_swipes=12)
    time.sleep(2)
    driver.save_screenshot("reference_contacts_after_next.png")
    print("✅ Reference Contacts 表单填写并提交完成")


def fill_basic_info_form(driver, max_swipes=15):
    """
    填写 Basic info 表单
    按页面顺序同步处理：滚动过程中先选下拉、再填文本，各自独立追踪进度
    """
    print("=== 开始填写 Basic info 表单 ===")

    wait_for_h5_text(driver, "Basic info", timeout=15)
    try:
        switch_to_real_webview(driver, timeout=10)
    except Exception:
        pass
    driver.execute_script("window.scrollTo(0, 0);")
    wait_for_h5_text(driver, "Select marital status", timeout=10)
    time.sleep(1.2)

    # 页面从上到下顺序：选项优先于同屏文本
    form_fields = [
        {"type": "select", "label": "Marital Status", "placeholder": "Select marital status", "value": "Single"},
        {"type": "select", "label": "Education Level", "placeholder": "Select education level", "value": "PHD"},
        {"type": "select", "label": "Purpose of Loan", "placeholder": "Select purpose of loan", "value": "Rent"},
        {"type": "text", "label": "Email ID", "value": "testauto123@gmail.com"},
        {"type": "text", "label": "Whatsapp", "value": "9811543210"},
        {"type": "text", "label": "Street address", "value": "Flat 5, Green Heights, MG Road"},
        {"type": "text", "label": "Town/City", "value": "Mumbai"},
        {"type": "select", "label": "State", "placeholder": "Select state", "value": "Bihar"},
        {"type": "text", "label": "Pincode", "value": "560001"},
        {"type": "select", "label": "Employment Type", "placeholder": "Select employment type", "value": "Student"},
        {"type": "select", "label": "Work Experience", "placeholder": "Select work experience", "value": "Over 2 Year"},
        {"type": "select", "label": "Salary Credit Day", "placeholder": "Select salary credit day", "value": "1"},
        {"type": "select", "label": "Monthly Income", "placeholder": "Select monthly income", "value": "₹0–10,000"},
    ]

    done_selects = set()
    done_texts = set()

    def count_progress():
        n_select = sum(1 for f in form_fields if f["type"] == "select")
        n_text = sum(1 for f in form_fields if f["type"] == "text")
        return len(done_selects), n_select, len(done_texts), n_text

    def process_select(field):
        label = field["label"]
        placeholder = field["placeholder"]
        option = field["value"]
        if label in done_selects:
            return False

        h5_hide_keyboard(driver)

        # 只有字段行里出现 expected 值（如 Single）才算已选，绝不误判
        if h5_select_has_value(driver, label, option):
            done_selects.add(label)
            print(f"✅ {label} 已有选中值: {option}")
            return True

        if not h5_open_select_dropdown(driver, label, placeholder):
            return False

        time.sleep(1.0)
        picked = h5_click_select_option(driver, option, modal_title=label)

        if picked:
            h5_dismiss_modal_if_open(driver)
            time.sleep(0.5)
            done_selects.add(label)
            print(f"✅ {label} 已确认选中: {picked}")
            return True

        h5_dismiss_modal_if_open(driver)
        print(f"⚠️ {label} 选择未生效，稍后重试")
        return False

    def process_text(field):
        label = field["label"]
        expected = field["value"]
        if label in done_texts:
            return False

        h5_scroll_to_label(driver, label)
        current = h5_get_text_value(driver, label)

        if current == expected:
            done_texts.add(label)
            return True

        if h5_fill_text_field(driver, label, expected, scroll=False):
            h5_hide_keyboard(driver)
            after = h5_get_text_value(driver, label)
            if after == expected:
                done_texts.add(label)
                return True
        return False

    n_select = sum(1 for f in form_fields if f["type"] == "select")
    n_text = sum(1 for f in form_fields if f["type"] == "text")

    # === 阶段1：只处理下拉，全部完成后再填文本 ===
    print("--- 阶段1：填写下拉选项 ---")
    h5_hide_keyboard(driver)
    swipe_count = 0
    while len(done_selects) < n_select and swipe_count <= max_swipes:
        progressed = False
        for field in form_fields:
            if field["type"] != "select" or field["label"] in done_selects:
                continue
            if process_select(field):
                progressed = True

        ds, _, _, _ = count_progress()
        print(f"选项进度: {ds}/{n_select}")

        if not progressed:
            swipe_up_h5(driver)
            swipe_count += 1
            if swipe_count % 4 == 0:
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.5)
        else:
            swipe_count = 0

    # === 阶段2：只处理文本 ===
    print("--- 阶段2：填写文本字段 ---")
    h5_hide_keyboard(driver)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)
    swipe_count = 0
    while len(done_texts) < n_text and swipe_count <= max_swipes:
        progressed = False
        for field in form_fields:
            if field["type"] != "text" or field["label"] in done_texts:
                continue
            if process_text(field):
                progressed = True

        _, _, dt, _ = count_progress()
        print(f"文本进度: {dt}/{n_text}")

        if not progressed:
            swipe_up_h5(driver)
            swipe_count += 1
        else:
            swipe_count = 0

    ds, ns, dt, nt = count_progress()
    print(f"最终进度: 选择项 {ds}/{ns}, 文本项 {dt}/{nt}")

    if ds < ns or dt < nt:
        print("⚠️ 表单未全部填写完成，请检查截图")
        driver.save_screenshot("basic_info_incomplete.png")

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(0.5)
    driver.save_screenshot("basic_info_before_next.png")
    h5_click_form_next(driver)
    time.sleep(2)
    driver.save_screenshot("basic_info_after_next.png")
    print("✅ Basic info 表单填写并提交完成")
