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

from loanadvisor.helpers.kyc.shared import (
    KYC_OCR_TEST_DATA,
    ensure_kyc_webview,
    generate_valid_pan,
    is_valid_pan,
    normalize_pan_value,
)
from loanadvisor.helpers.native.permissions import handle_permission_popup
from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import (
    h5_click_text_and_parents,
    h5_fill_text_field,
    h5_hide_keyboard,
    h5_tap_at,
    h5_vue_click_element,
    h5_w3c_tap_element,
)
from loanadvisor.helpers.webview.switcher import switch_to_real_webview

def h5_swipe_at(driver, x1, y1, x2, y2, duration=400):
    """WebView 坐标滑动（用于日期滚轮）"""
    try:
        driver.execute_script(
            "mobile: dragGesture",
            {
                "startX": int(x1),
                "startY": int(y1),
                "endX": int(x2),
                "endY": int(y2),
                "speed": max(500, int(duration)),
            },
        )
        return True
    except Exception:
        pass
    try:
        driver.execute_script(
            """
            const x1 = arguments[0], y1 = arguments[1], x2 = arguments[2], y2 = arguments[3];
            const el = document.elementFromPoint(x1, y1);
            if (!el) return false;
            function fire(type, x, y) {
                el.dispatchEvent(new TouchEvent(type, {
                    bubbles: true, cancelable: true,
                    touches: [{clientX: x, clientY: y}],
                    targetTouches: [{clientX: x, clientY: y}],
                    changedTouches: [{clientX: x, clientY: y}],
                }));
            }
            fire('touchstart', x1, y1);
            fire('touchmove', x2, y2);
            fire('touchend', x2, y2);
            return true;
            """,
            int(x1),
            int(y1),
            int(x2),
            int(y2),
        )
        return True
    except Exception:
        return False


def _kyc_confirm_modal_js():
    return """
        function getKycConfirmModal() {
            let best = null;
            let bestArea = 0;
            for (const el of document.querySelectorAll('div, section, form')) {
                const t = (el.innerText || '');
                if (!t.includes('Confirm your info')) continue;
                const r = el.getBoundingClientRect();
                if (r.width < 200 || r.height < 180) continue;
                const area = r.width * r.height;
                if (area > bestArea) {
                    bestArea = area;
                    best = el;
                }
            }
            return best || document.body;
        }

        function isPlaceholderValue(labelKeyword, line) {
            const l = (line || '').trim().toLowerCase();
            const lk = (labelKeyword || '').trim().toLowerCase();
            if (!l || l === lk) return true;
            if (l === 'pan card number') return true;
            if (l === 'date of birth') return true;
            if (l === 'full name') return true;
            if (l.startsWith('select ')) return true;
            if (l.includes('e.g.')) return true;
            return false;
        }

        function getKycModalFieldRow(labelKeyword) {
            const modal = getKycConfirmModal();
            const hits = [];
            for (const el of modal.querySelectorAll('label, div, span, p')) {
                const t = (el.innerText || '').trim();
                if (!t.includes(labelKeyword)) continue;
                if (t.length > labelKeyword.length + 50) continue;
                let node = el;
                for (let i = 0; i < 10; i++) {
                    if (!node) break;
                    const ct = (node.innerText || '').trim();
                    const r = node.getBoundingClientRect();
                    if (!ct.includes(labelKeyword)) {
                        node = node.parentElement;
                        continue;
                    }
                    if (r.height < 28 || r.height > 220 || r.width < 80) {
                        node = node.parentElement;
                        continue;
                    }
                    hits.push({node, top: r.top});
                    break;
                }
            }
            hits.sort((a, b) => a.top - b.top);
            return hits.length ? hits[0].node : null;
        }

        function getKycModalFieldValue(labelKeyword) {
            const row = getKycModalFieldRow(labelKeyword);
            if (!row) return '';
            const inp = row.querySelector('input, textarea');
            if (inp) {
                const v = (inp.value || '').trim();
                if (v && !isPlaceholderValue(labelKeyword, v)) return v;
            }
            const lines = (row.innerText || '').trim().split('\\n').map(s => s.trim()).filter(Boolean);
            for (const line of lines) {
                if (isPlaceholderValue(labelKeyword, line)) continue;
                if (line.length >= 2) return line;
            }
            return '';
        }

        function isVisibleEl(el) {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            if (r.width < 8 || r.height < 8) return false;
            if (r.bottom <= 0 || r.top >= window.innerHeight + 2) return false;
            const st = window.getComputedStyle(el);
            if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) === 0) {
                return false;
            }
            return true;
        }

        function getVisiblePickerColumns() {
            const cols = document.querySelectorAll('.van-picker-column, .van-picker__column');
            return Array.from(cols).filter(isVisibleEl);
        }

        function getDatePickerRoot() {
            for (const el of document.querySelectorAll('.van-popup, .van-picker, .van-datetime-picker, .van-picker__columns')) {
                const t = (el.innerText || '');
                if (!t.includes('Date')) continue;
                if (!isVisibleEl(el)) continue;
                const r = el.getBoundingClientRect();
                if (r.height < 80 || r.width < 180) continue;
                if (getVisiblePickerColumns().length >= 3) return el;
            }
            for (const el of document.querySelectorAll('.van-popup, .van-picker, div, section')) {
                const t = (el.innerText || '');
                if (!t.includes('Date')) continue;
                if (!isVisibleEl(el)) continue;
                const r = el.getBoundingClientRect();
                if (r.height < 120 || r.width < 200) continue;
                if (r.top > window.innerHeight * 0.92) continue;
                return el;
            }
            return null;
        }

        function getPickerColumns() {
            const visible = getVisiblePickerColumns();
            return visible.length >= 3 ? visible : [];
        }

        function pickInPickerColumn(columnIndex, value) {
            const variants = new Set([
                String(value),
                String(value).padStart(2, '0'),
                String(parseInt(value, 10)),
            ]);
            const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
            if (/^\\d{1,2}$/.test(String(value))) {
                const idx = parseInt(value, 10) - 1;
                if (idx >= 0 && idx < 12) {
                    variants.add(monthNames[idx]);
                    variants.add(String(idx + 1));
                }
            }
            const cols = getPickerColumns();
            if (cols.length <= columnIndex) return false;
            const col = cols[columnIndex];
            for (const el of col.querySelectorAll('li, div, span, ul, p')) {
                const t = (el.innerText || '').trim();
                if (!variants.has(t)) continue;
                const r = el.getBoundingClientRect();
                if (r.height < 4 || r.width < 4) continue;
                el.scrollIntoView({block: 'center', behavior: 'instant'});
                el.click();
                return true;
            }
            return false;
        }

        function getPickerColumnRect(columnIndex) {
            const cols = getPickerColumns();
            if (cols.length <= columnIndex) return null;
            const r = cols[columnIndex].getBoundingClientRect();
            return {
                x: r.left + r.width / 2,
                y1: r.top + r.height * 0.72,
                y2: r.top + r.height * 0.28,
                top: r.top,
                height: r.height,
            };
        }

        function getKycDobValueTarget() {
            const row = getKycModalFieldRow('Date of Birth');
            if (!row) return null;
            row.scrollIntoView({block: 'center', behavior: 'instant'});

            for (const el of row.querySelectorAll('div, span, p, label')) {
                const t = (el.innerText || '').trim();
                if (!t || t.includes('Date of Birth') || t.includes('*')) continue;
                if (/\\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\b/i.test(t)
                    && /\\d{1,2}/.test(t) && /\\d{4}/.test(t)) {
                    const r = el.getBoundingClientRect();
                    if (r.height < 6 || r.width < 16) continue;
                    return {el, mode: 'value'};
                }
            }

            for (const el of row.querySelectorAll('i, svg, [class*="arrow"], [class*="icon"], span')) {
                const r = el.getBoundingClientRect();
                const rr = row.getBoundingClientRect();
                if (r.width < 4 || r.height < 4) continue;
                if (r.left >= rr.left + rr.width * 0.78) {
                    return {el, mode: 'chevron'};
                }
            }

            return {el: row, mode: 'row'};
        }

        function openKycDatePickerTap() {
            const target = getKycDobValueTarget();
            if (!target) return null;
            const el = target.el;
            el.scrollIntoView({block: 'center', behavior: 'instant'});
            const r = el.getBoundingClientRect();
            let y = r.top + r.height / 2;
            if (target.mode === 'row') {
                y = r.top + r.height * 0.72;
            }
            return {
                x: r.right - Math.max(28, r.width * 0.05),
                y: y,
                cx: r.left + r.width * 0.55,
                cy: y,
                mode: target.mode,
            };
        }

        function openKycDatePickerClick() {
            const target = getKycDobValueTarget();
            if (!target) return false;
            const el = target.el;
            el.scrollIntoView({block: 'center', behavior: 'instant'});
            el.click();
            let p = el;
            for (let i = 0; i < 6; i++) {
                if (!p.parentElement) break;
                p = p.parentElement;
                const t = (p.innerText || '');
                if (t.includes('Date of Birth')) {
                    p.click();
                    try {
                        const r = p.getBoundingClientRect();
                        const hit = document.elementFromPoint(r.right - 24, r.top + r.height * 0.72);
                        if (hit) hit.click();
                    } catch (e) {}
                    return true;
                }
            }
            return true;
        }

        function openKycPanFieldTap() {
            const row = getKycModalFieldRow('PAN card number') || getKycModalFieldRow('PAN');
            if (!row) return null;
            row.scrollIntoView({block: 'center', behavior: 'instant'});
            const r = row.getBoundingClientRect();
            const lines = (row.innerText || '').split('\\n');
            let y = r.top + r.height * 0.72;
            if (lines.length >= 2) y = r.top + r.height * 0.62;
            return {x: r.left + r.width * 0.55, y: y, cx: r.left + r.width / 2, cy: y};
        }

        function findPanInputInModal() {
            const modal = getKycConfirmModal();
            for (const inp of modal.querySelectorAll('input, textarea, [contenteditable="true"]')) {
                const ph = (inp.placeholder || inp.getAttribute('placeholder') || '').toLowerCase();
                const name = (inp.name || inp.id || '').toLowerCase();
                if (ph.includes('pan') || name.includes('pan')) return inp;
            }
            const inputs = modal.querySelectorAll('input, textarea');
            for (let i = inputs.length - 1; i >= 0; i--) {
                const inp = inputs[i];
                const ph = (inp.placeholder || '').toLowerCase();
                const v = (inp.value || '').trim();
                if (ph.includes('pan') || (!v && inp.offsetParent !== null)) return inp;
            }
            return null;
        }

        function fillKycPanInput(value) {
            let inp = findPanInputInModal();
            if (!inp) return false;
            inp.scrollIntoView({block: 'center', behavior: 'instant'});
            inp.focus();
            inp.click();
            const proto = inp.tagName === 'TEXTAREA'
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value');
            const v = String(value).trim().toUpperCase();
            if (setter && setter.set) {
                setter.set.call(inp, '');
                inp.dispatchEvent(new Event('input', {bubbles: true}));
                setter.set.call(inp, v);
            } else {
                inp.value = v;
            }
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            inp.dispatchEvent(new Event('change', {bubbles: true}));
            inp.dispatchEvent(new Event('blur', {bubbles: true}));
            return (inp.value || '').trim().toUpperCase() === v;
        }

        function clearKycPanInput() {
            const inp = findPanInputInModal();
            if (!inp) return false;
            inp.focus();
            inp.click();
            const proto = window.HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value');
            if (setter && setter.set) {
                setter.set.call(inp, '');
            } else {
                inp.value = '';
            }
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            return true;
        }

        function pickDateWheelValue(value) {
            const variants = new Set([
                String(value),
                String(value).padStart(2, '0'),
                String(parseInt(value, 10)),
            ]);
            let best = null;
            for (const el of document.querySelectorAll('div, span, li, p')) {
                const t = (el.innerText || '').trim();
                if (!variants.has(t)) continue;
                const r = el.getBoundingClientRect();
                if (r.top < window.innerHeight * 0.18 || r.top > window.innerHeight * 0.82) continue;
                if (r.height < 8 || r.height > 80) continue;
                const dist = Math.abs(r.top + r.height / 2 - window.innerHeight * 0.45);
                if (!best || dist < best.dist) {
                    best = {el, dist};
                }
            }
            if (best) {
                best.el.scrollIntoView({block: 'center', behavior: 'instant'});
                best.el.click();
                return true;
            }
            return false;
        }

        function findDatePickerConfirmEl() {
            const root = getDatePickerRoot();
            const scopes = [];
            if (root) scopes.push(root);
            for (const popup of document.querySelectorAll('.van-popup--bottom, .van-popup')) {
                const t = (popup.innerText || '');
                if (!isVisibleEl(popup) || !t.includes('Date')) continue;
                scopes.push(popup);
            }
            if (!scopes.length) scopes.push(document.body);

            for (const sel of ['.van-picker__confirm', '.van-picker-confirm', '[class*="confirm"]']) {
                for (const scope of scopes) {
                    const btn = scope.querySelector(sel);
                    if (btn && isVisibleEl(btn)) return btn;
                }
            }

            let best = null;
            let bestTop = Infinity;
            for (const scope of scopes) {
                for (const el of scope.querySelectorAll('button, div, span, p, a')) {
                    const t = (el.innerText || '').trim();
                    if (t !== 'Confirm' && t !== 'OK' && t !== 'Done') continue;
                    if (!isVisibleEl(el)) continue;
                    const r = el.getBoundingClientRect();
                    if (r.top > window.innerHeight * 0.9) continue;
                    if (r.width < 10 || r.height < 8) continue;
                    if (r.top < bestTop) {
                        bestTop = r.top;
                        best = el;
                    }
                }
            }
            return best;
        }

        function getDatePickerConfirmTap() {
            const btn = findDatePickerConfirmEl();
            if (btn) {
                const r = btn.getBoundingClientRect();
                return {x: r.left + r.width / 2, y: r.top + r.height / 2, mode: 'btn'};
            }
            const root = getDatePickerRoot();
            if (root) {
                const r = root.getBoundingClientRect();
                return {x: r.right - 42, y: r.top + 26, mode: 'toolbar'};
            }
            return null;
        }

        function clickDatePickerConfirm() {
            const btn = findDatePickerConfirmEl();
            if (!btn) return false;
            btn.scrollIntoView({block: 'center', behavior: 'instant'});
            btn.click();
            let p = btn;
            for (let i = 0; i < 3; i++) {
                if (!p.parentElement) break;
                p = p.parentElement;
                p.click();
            }
            return true;
        }

        function isDatePickerOpen() {
            return getVisiblePickerColumns().length >= 3;
        }

        function scanKycConfirmForm() {
            const modal = getKycConfirmModal();
            const body = modal.innerText || '';
            let pan = '';
            const inp = findPanInputInModal();
            if (inp) pan = (inp.value || '').trim().toUpperCase();
            if (!pan) {
                for (const el of modal.querySelectorAll('input, textarea')) {
                    const v = (el.value || '').trim().toUpperCase();
                    if (/^[A-Z]{5}\\d{4}[A-Z]$/.test(v)) {
                        pan = v;
                        break;
                    }
                }
            }
            if (!pan) {
                const m = body.match(/[A-Z]{5}\\d{4}[A-Z]/);
                if (m) pan = m[0];
            }

            let dob = getKycModalFieldValue('Date of Birth');
            if (!dob || isPlaceholderValue('Date of Birth', dob)) {
                const row = getKycModalFieldRow('Date of Birth');
                if (row) {
                    for (const line of (row.innerText || '').split('\\n')) {
                        const t = line.trim();
                        if (!t || isPlaceholderValue('Date of Birth', t)) continue;
                        if (/\\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\b/i.test(t)) {
                            dob = t;
                            break;
                        }
                    }
                }
            }

            return {
                dob: dob || '',
                pan: pan || '',
                onConfirmModal: body.includes('Confirm your info'),
                hasNext: body.includes('Next'),
                pickerOpen: getVisiblePickerColumns().length >= 3,
            };
        }
    """


def _parse_dob_parts(dob):
    """解析 31/07/2000 → (day, month, year)"""
    parts = dob.replace("-", "/").split("/")
    if len(parts) != 3:
        return "01", "01", "2000"
    if len(parts[0]) == 4:
        return parts[2].zfill(2), parts[1].zfill(2), parts[0]
    return parts[0].zfill(2), parts[1].zfill(2), parts[2]


_MONTH_ABBR = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _month_picker_variants(month):
    """滚轮月份列可能是 Jul 而非 07"""
    variants = [month, str(int(month))]
    try:
        idx = int(month) - 1
        if 0 <= idx < 12:
            variants.append(_MONTH_ABBR[idx])
    except (ValueError, TypeError):
        pass
    seen = set()
    out = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _h5_tap_kyc_dob_open(driver):
    """多种方式点击 DOB 值区域打开滚轮"""
    js = _kyc_confirm_modal_js()

    tap = driver.execute_script(js + "return openKycDatePickerTap();")
    if tap:
        h5_tap_at(driver, tap["x"], tap["y"])
        time.sleep(0.3)
        h5_tap_at(driver, tap["cx"], tap["cy"])
        try:
            el = driver.execute_script(
                js
                + """
                const t = openKycDatePickerTap();
                if (!t) return null;
                return document.elementFromPoint(t.cx, t.cy);
                """
            )
            if el:
                h5_vue_click_element(driver, el)
                h5_w3c_tap_element(driver, el)
        except Exception:
            pass
        driver.execute_script(js + "return openKycDatePickerClick();")
        return True

    driver.execute_script(js + "return openKycDatePickerClick();")
    return False


def h5_get_kyc_modal_field_value(driver, label_keyword):
    return driver.execute_script(
        _kyc_confirm_modal_js()
        + "return getKycModalFieldValue(arguments[0]);",
        label_keyword,
    ) or ""


def h5_kyc_dob_matches(driver, dob):
    """Date of Birth 是否已是目标日期（排除 Jan 1 默认占位）"""
    current = h5_get_kyc_modal_field_value(driver, "Date of Birth")
    if not current:
        return False
    low = current.lower()
    if "date of birth" in low or "e.g." in low:
        return False

    day, month, year = _parse_dob_parts(dob)
    if year not in current:
        return False

    month_map = {
        "01": "jan", "02": "feb", "03": "mar", "04": "apr",
        "05": "may", "06": "jun", "07": "jul", "08": "aug",
        "09": "sep", "10": "oct", "11": "nov", "12": "dec",
    }
    month_hint = month_map.get(month, "")
    day_int = str(int(day))

    has_day = day in current or day_int in current or f", {day_int}," in low
    has_month = month in current or month_hint in low

    if has_day and has_month:
        return True

    if ("jan 1" in low or "jan 01" in low) and day in ("01", "1") and month == "01":
        return True
    return False


def _h5_is_date_picker_open(driver):
    """严格判断日期滚轮是否已打开（必须有 3 列 picker）"""
    return driver.execute_script(
        _kyc_confirm_modal_js()
        + "return isDatePickerOpen();"
    )


def _h5_open_kyc_date_picker(driver):
    """点击 Date of Birth 打开日期滚轮（多策略）"""
    ensure_kyc_webview(driver)
    h5_hide_keyboard(driver)

    js = _kyc_confirm_modal_js()
    driver.execute_script(
        js
        + """
        const row = getKycModalFieldRow('Date of Birth');
        if (row) row.scrollIntoView({block: 'center', behavior: 'instant'});
        """
    )
    time.sleep(0.5)

    current = h5_get_kyc_modal_field_value(driver, "Date of Birth")

    for attempt in range(5):
        if _h5_is_date_picker_open(driver):
            print("✅ 日期选择器已打开")
            return True

        if current and len(current) > 5:
            for part in (current, current.split(",")[0].strip()):
                if h5_click_text_and_parents(driver, part, timeout=2):
                    time.sleep(1.0)
                    if _h5_is_date_picker_open(driver):
                        print(f"✅ 日期选择器已打开(点击: {part})")
                        return True

        _h5_tap_kyc_dob_open(driver)
        time.sleep(1.0)
        if _h5_is_date_picker_open(driver):
            print("✅ 日期选择器已打开(行点击)")
            return True

        h5_click_text_and_parents(driver, "Date of Birth", timeout=3)
        time.sleep(1.0)
        if _h5_is_date_picker_open(driver):
            print("✅ 日期选择器已打开(标签点击)")
            return True

        time.sleep(0.5)

    driver.save_screenshot("kyc_dob_picker_not_open.png")
    return False


def _h5_click_date_picker_confirm(driver, dob=None):
    """点击日期滚轮 Confirm；以滚轮关闭或 DOB 已更新为成功"""
    js = _kyc_confirm_modal_js()

    for attempt in range(5):
        if not _h5_is_date_picker_open(driver):
            print("✅ 日期选择器已 Confirm")
            return True

        clicked = False
        if driver.execute_script(js + "return clickDatePickerConfirm();"):
            clicked = True
        else:
            tap = driver.execute_script(js + "return getDatePickerConfirmTap();")
            if tap:
                h5_tap_at(driver, tap["x"], tap["y"])
                clicked = True
                try:
                    btn = driver.execute_script(js + "return findDatePickerConfirmEl();")
                    if btn:
                        h5_vue_click_element(driver, btn)
                        h5_w3c_tap_element(driver, btn)
                except Exception:
                    pass
            elif h5_click_text_and_parents(
                driver, "Confirm", timeout=2, bottom_sheet_only=True
            ):
                clicked = True
            elif h5_click_modal_button(driver, "Confirm", timeout=2):
                clicked = True

        time.sleep(0.9)
        h5_hide_keyboard(driver)

        if not _h5_is_date_picker_open(driver):
            print("✅ 日期选择器已 Confirm")
            return True

        if dob and h5_kyc_dob_matches(driver, dob):
            print("✅ Date of Birth 滚轮值已生效")
            return True

        current = h5_get_kyc_modal_field_value(driver, "Date of Birth")
        if current and "jan 1" not in current.lower():
            print(f"✅ Date of Birth 已更新: {current}")
            return True

        if clicked:
            time.sleep(0.5)

    return False


def _h5_pick_picker_column(driver, column_index, value, swipe_times=0):
    """在 van-picker 指定列选择值，必要时滑动滚轮"""
    js = _kyc_confirm_modal_js()
    picked = driver.execute_script(
        js + "return pickInPickerColumn(arguments[0], arguments[1]);",
        column_index,
        value,
    )
    if picked:
        return True

    picked = driver.execute_script(
        js + "return pickDateWheelValue(arguments[0]);", value
    )
    if picked:
        return True

    rect = driver.execute_script(
        js + "return getPickerColumnRect(arguments[0]);", column_index
    )
    if not rect:
        return False

    for _ in range(max(1, swipe_times)):
        h5_swipe_at(driver, rect["x"], rect["y1"], rect["x"], rect["y2"])
        time.sleep(0.35)
        if driver.execute_script(
            js + "return pickInPickerColumn(arguments[0], arguments[1]);",
            column_index,
            value,
        ):
            return True
        if driver.execute_script(
            js + "return pickDateWheelValue(arguments[0]);", value
        ):
            return True
    return False


def h5_pick_kyc_date_of_birth(driver, dob):
    """Date of Birth：打开滚轮 → 选年/月/日 → Confirm"""
    if h5_kyc_dob_matches(driver, dob):
        print(f"⏭️ Date of Birth 已是目标值: {h5_get_kyc_modal_field_value(driver, 'Date of Birth')}")
        return True

    day, month, year = _parse_dob_parts(dob)
    print(f"--- 选择 Date of Birth: {day}/{month}/{year} ---")

    if not _h5_open_kyc_date_picker(driver):
        print("⚠️ 未能打开日期选择器")
        return False

    if not _h5_is_date_picker_open(driver):
        print("⚠️ 日期选择器未真正打开（无滚轮列）")
        driver.save_screenshot("kyc_dob_picker_not_open.png")
        return False

    time.sleep(0.6)
    _h5_pick_picker_column(driver, 0, year, swipe_times=2)
    time.sleep(0.4)
    for month_val in _month_picker_variants(month):
        if _h5_pick_picker_column(driver, 1, month_val, swipe_times=8):
            break
    time.sleep(0.4)
    _h5_pick_picker_column(driver, 2, day, swipe_times=12)
    time.sleep(0.5)

    if not _h5_click_date_picker_confirm(driver, dob=dob):
        print("⚠️ 未能点击日期选择器 Confirm，检查 DOB 是否已更新...")
        driver.save_screenshot("kyc_dob_confirm_fail.png")
        if _h5_is_date_picker_open(driver):
            _h5_click_date_picker_confirm(driver, dob=dob)

    time.sleep(1.0)
    h5_hide_keyboard(driver)

    if h5_kyc_dob_matches(driver, dob):
        print(f"✅ Date of Birth 已选择: {h5_get_kyc_modal_field_value(driver, 'Date of Birth')}")
        return True

    current = h5_get_kyc_modal_field_value(driver, "Date of Birth")
    if current and "jan 1" not in current.lower():
        print(f"✅ Date of Birth 已更新: {current}")
        return True

    print(f"⚠️ Date of Birth 选择后仍未匹配，当前: {current or '(空)'}")
    driver.save_screenshot("kyc_dob_pick_fail.png")
    return False


def _h5_get_pan_input_value(driver):
    raw = driver.execute_script(
        _kyc_confirm_modal_js()
        + """
        const inp = findPanInputInModal();
        return inp ? (inp.value || '').trim().toUpperCase() : '';
        """
    ) or ""
    if not raw:
        return ""
    return normalize_pan_value(raw)


def h5_fill_kyc_pan(driver, pan_number):
    """PAN card number：恢复可用填写逻辑，成功即停，避免重复输入"""
    pan_number = pan_number.strip().upper()
    if not is_valid_pan(pan_number):
        pan_number = generate_valid_pan()

    current = _h5_get_pan_input_value(driver)
    if not is_valid_pan(current):
        display = h5_get_kyc_modal_field_value(driver, "PAN card number")
        if display and display.lower() != "pan card number":
            current = normalize_pan_value(display)
    if is_valid_pan(current):
        print(f"⏭️ PAN card number 已有: {current}")
        return True

    js = _kyc_confirm_modal_js()
    tap = driver.execute_script(js + "return openKycPanFieldTap();")
    if tap:
        h5_tap_at(driver, tap["x"], tap["y"])
        time.sleep(0.5)
        h5_tap_at(driver, tap["cx"], tap["cy"])
        time.sleep(0.4)

    driver.execute_script(js + "return fillKycPanInput(arguments[0]);", pan_number)
    time.sleep(0.3)
    after = _h5_get_pan_input_value(driver)
    if is_valid_pan(after):
        print(f"✅ PAN card number 已填: {after}")
        return True

    driver.execute_script(js + "return clearKycPanInput();")
    time.sleep(0.2)
    try:
        inp_el = driver.execute_script(js + "return findPanInputInModal();")
        if inp_el:
            inp_el.clear()
            inp_el.send_keys(pan_number)
            time.sleep(0.3)
            after = normalize_pan_value(inp_el.get_attribute("value") or "")
            if is_valid_pan(after):
                print(f"✅ PAN card number 已填: {after}")
                return True
    except Exception:
        pass

    h5_hide_keyboard(driver)
    time.sleep(0.4)

    after = _h5_get_pan_input_value(driver)
    if is_valid_pan(after):
        print(f"✅ PAN card number 已填: {after}")
        return True

    print(f"⚠️ PAN card number 填写失败，当前值: {after or '(空)'}")
    driver.save_screenshot("kyc_pan_fill_fail.png")
    return False


def _h5_scan_kyc_confirm_state(driver):
    return (
        driver.execute_script(
            _kyc_confirm_modal_js() + "return scanKycConfirmForm();"
        )
        or {}
    )


def _h5_dob_looks_filled(dob_text, target_dob=None):
    """DOB 在界面上看起来已填写（非 Jan 1 默认占位）"""
    if not dob_text:
        return False
    low = dob_text.lower()
    if "date of birth" in low or "e.g." in low:
        return False
    if "jan 1" in low or "jan 01" in low:
        if target_dob:
            day, month, _ = _parse_dob_parts(target_dob)
            if day in ("01", "1") and month == "01":
                return True
        return False
    if any(m.lower() in low for m in _MONTH_ABBR):
        return True
    return len(dob_text.strip()) >= 6


def _h5_read_kyc_dob_pan(driver):
    """多通道读取 Confirm 弹窗 DOB / PAN（降低检测误差）"""
    state = _h5_scan_kyc_confirm_state(driver)
    dob = state.get("dob") or h5_get_kyc_modal_field_value(driver, "Date of Birth")
    pan = state.get("pan") or _h5_get_pan_input_value(driver)
    if pan:
        pan = normalize_pan_value(pan)
    if not is_valid_pan(pan):
        display = h5_get_kyc_modal_field_value(driver, "PAN card number")
        if display and display.lower() not in ("pan card number", "pan"):
            pan = normalize_pan_value(display)
    return dob, pan, state


def h5_kyc_confirm_form_likely_ready(driver, pan_number, dob):
    """
    宽松检测：界面看起来 DOB + PAN 已填好。
    用于严格检测误报时仍允许点 Next。
    """
    if _h5_is_date_picker_open(driver):
        return False, {"reason": "picker_still_open"}

    dob_text, pan_text, state = _h5_read_kyc_dob_pan(driver)
    dob_ok = _h5_dob_looks_filled(dob_text, dob) or h5_kyc_dob_matches(driver, dob)
    pan_ok = is_valid_pan(pan_text or "")

    if not pan_ok and pan_number and is_valid_pan(pan_number):
        modal_text = driver.execute_script(
            _kyc_confirm_modal_js()
            + """
            const m = getKycConfirmModal();
            return (m.innerText || '').toUpperCase();
            """
        ) or ""
        if pan_number.upper() in modal_text:
            pan_ok = True
            pan_text = pan_number.upper()

    info = {"dob": dob_text, "pan": pan_text, "state": state}
    return dob_ok and pan_ok, info


def h5_kyc_confirm_form_ready(driver, pan_number, dob):
    """确认 DOB 与 PAN 均已完成才允许点 Next"""
    dob_text, pan_text, _ = _h5_read_kyc_dob_pan(driver)

    dob_ok = h5_kyc_dob_matches(driver, dob)
    if not dob_ok:
        dob_ok = _h5_dob_looks_filled(dob_text, dob)

    pan_ok = is_valid_pan(pan_text or "")

    if not dob_ok:
        print(f"⚠️ Date of Birth 未完成: {dob_text or '(空)'}")
    if not pan_ok:
        print(f"⚠️ PAN card number 未完成: {pan_text or '(空)'}")
    return dob_ok and pan_ok


def h5_fill_kyc_dob(driver, dob):
    """兼容旧调用：走日期选择器"""
    return h5_pick_kyc_date_of_birth(driver, dob)


def h5_fill_kyc_confirm_form(driver, full_name=None, date_of_birth=None, pan_number=None):
    """OCR 确认页：补填 Full Name / DOB(选择器) / PAN(输入)，全部完成才返回 True"""
    ensure_kyc_webview(driver, timeout=15)
    wait_for_h5_text(driver, "Confirm your info", timeout=30)
    time.sleep(1.0)

    full_name = full_name or KYC_OCR_TEST_DATA["full_name"]
    date_of_birth = date_of_birth or KYC_OCR_TEST_DATA["date_of_birth"]
    pan_number = (pan_number or KYC_OCR_TEST_DATA["pan_number"]).strip().upper()
    if not is_valid_pan(pan_number):
        pan_number = generate_valid_pan()
        print(f"使用生成的 PAN: {pan_number}")

    aadhaar = h5_get_kyc_modal_field_value(driver, "Aadhaar Number")
    if aadhaar:
        print(f"⏭️ Aadhaar Number OCR 已有: {aadhaar[:4]}****")

    gender = h5_get_kyc_modal_field_value(driver, "Gender")
    if gender:
        print(f"⏭️ Gender OCR 已有: {gender}")

    name_val = h5_get_kyc_modal_field_value(driver, "Full Name")
    if not name_val or name_val.lower() in ("full name", "e.g."):
        h5_fill_text_field(driver, "Full Name", full_name, scroll=False)
    else:
        print(f"⏭️ Full Name 已有: {name_val}")

    h5_pick_kyc_date_of_birth(driver, date_of_birth)
    h5_fill_kyc_pan(driver, pan_number)

    if _h5_is_date_picker_open(driver):
        _h5_click_date_picker_confirm(driver, dob=date_of_birth)

    h5_hide_keyboard(driver)
    time.sleep(0.5)

    ready = h5_kyc_confirm_form_ready(driver, pan_number, date_of_birth)
    if not ready:
        if not h5_kyc_dob_matches(driver, date_of_birth):
            current_dob, _, _ = _h5_read_kyc_dob_pan(driver)
            if not _h5_dob_looks_filled(current_dob, date_of_birth):
                h5_pick_kyc_date_of_birth(driver, date_of_birth)
        _, pan_now, _ = _h5_read_kyc_dob_pan(driver)
        if not is_valid_pan(pan_now or ""):
            h5_fill_kyc_pan(driver, pan_number)
        if _h5_is_date_picker_open(driver):
            _h5_click_date_picker_confirm(driver, dob=date_of_birth)
        h5_hide_keyboard(driver)
        time.sleep(0.5)
        ready = h5_kyc_confirm_form_ready(driver, pan_number, date_of_birth)

    if not ready:
        likely, info = h5_kyc_confirm_form_likely_ready(
            driver, pan_number, date_of_birth
        )
        if likely:
            print(
                f"⚠️ 严格检测未通过，但界面已显示 "
                f"DOB={info.get('dob')} PAN={info.get('pan')}，视为已完成"
            )
            ready = True

    if not ready:
        driver.save_screenshot("kyc_confirm_incomplete.png")
        print("⚠️ Confirm your info 表单未全部完成")
    return ready
