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

from loanadvisor.helpers.kyc.shared import KYC_BANK_TEST_DATA
from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import h5_click_bottom_button, h5_click_form_next, h5_hide_keyboard, swipe_up_h5
from loanadvisor.helpers.webview.switcher import switch_to_real_webview

def _h5_bank_field_js():
    return """
        function getBankFieldRow(labelKeyword) {
            for (const el of document.querySelectorAll('label, div, span, p')) {
                const t = (el.innerText || '').trim();
                if (labelKeyword === 'Account No.') {
                    if (!t.includes('Account No')) continue;
                    if (/confirmation/i.test(t)) continue;
                } else if (/confirmation/i.test(labelKeyword)) {
                    if (!/confirmation/i.test(t) || !t.includes('Account')) continue;
                } else if (!t.includes(labelKeyword)) {
                    continue;
                }
                if (t.length > labelKeyword.length + 45) continue;

                let node = el;
                for (let i = 0; i < 10; i++) {
                    if (!node) break;
                    const ct = (node.innerText || '').trim();
                    const r = node.getBoundingClientRect();
                    if (!ct.includes(labelKeyword === 'Account No.' ? 'Account No' : labelKeyword.split('.')[0])) {
                        node = node.parentElement;
                        continue;
                    }
                    if (labelKeyword === 'Account No.' && /confirmation/i.test(ct)) {
                        node = node.parentElement;
                        continue;
                    }
                    if (r.height < 28 || r.height > 220 || r.width < 80) {
                        node = node.parentElement;
                        continue;
                    }
                    return node;
                }
            }
            return null;
        }

        function findBankInput(labelKeyword) {
            const row = getBankFieldRow(labelKeyword);
            if (row) {
                const inp = row.querySelector('input:not([type="checkbox"]), textarea');
                if (inp) return inp;
            }
            if (labelKeyword === 'IFSC code') {
                for (const el of document.querySelectorAll('input, textarea')) {
                    const ph = (el.placeholder || el.getAttribute('placeholder') || '').toLowerCase();
                    if (ph.includes('ifsc') || ph.includes('11-character')) return el;
                }
            }
            if (labelKeyword === 'Account No.') {
                for (const el of document.querySelectorAll('input, textarea')) {
                    const ph = (el.placeholder || el.getAttribute('placeholder') || '').toLowerCase();
                    if (ph.includes('9-18') && !ph.includes('re-enter')) return el;
                }
            }
            if (/confirmation/i.test(labelKeyword)) {
                for (const el of document.querySelectorAll('input, textarea')) {
                    const ph = (el.placeholder || el.getAttribute('placeholder') || '').toLowerCase();
                    if (ph.includes('re-enter')) return el;
                }
            }
            return null;
        }

        function clearBankField(labelKeyword) {
            const inp = findBankInput(labelKeyword);
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
            } else {
                inp.value = '';
            }
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            inp.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        }

        function getBankFieldValue(labelKeyword) {
            const inp = findBankInput(labelKeyword);
            return inp ? (inp.value || '').trim() : '';
        }

        function fillBankField(labelKeyword, value) {
            const inp = findBankInput(labelKeyword);
            if (!inp) return false;
            inp.scrollIntoView({block: 'center', behavior: 'instant'});
            inp.focus();
            inp.click();
            const proto = inp.tagName === 'TEXTAREA'
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value');
            const v = String(value);
            if (setter && setter.set) {
                setter.set.call(inp, '');
                inp.dispatchEvent(new Event('input', {bubbles: true}));
                setter.set.call(inp, v);
            } else {
                inp.value = '';
                inp.value = v;
            }
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            inp.dispatchEvent(new Event('change', {bubbles: true}));
            inp.dispatchEvent(new Event('blur', {bubbles: true}));
            return (inp.value || '').trim() === v;
        }

        function ensureBankCheckboxChecked() {
            for (const el of document.querySelectorAll('input[type="checkbox"]')) {
                if (!el.checked) {
                    el.click();
                    el.checked = true;
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
                return true;
            }
            for (const el of document.querySelectorAll('.van-checkbox, [class*="checkbox"]')) {
                const r = el.getBoundingClientRect();
                if (r.width < 8 || r.height < 8) continue;
                const cls = (el.className || '').toString();
                if (cls.includes('checked') || cls.includes('active')) return true;
                el.click();
                return true;
            }
            return false;
        }
    """


def ensure_bank_webview(driver, timeout=15):
    """切换到 Bank information WebView"""
    for keyword in ("bank", "identity", "KYCProcess"):
        try:
            switch_to_real_webview(driver, keyword=keyword, timeout=max(5, timeout // 3))
            time.sleep(0.8)
            return
        except Exception:
            pass
    switch_to_real_webview(driver, timeout=timeout)
    time.sleep(0.8)


def h5_scroll_up_find_bank_field(driver, label_keyword, max_swipes=10):
    """字段找不到时向上滑动页面查找（露出下方表单项）"""
    js = _h5_bank_field_js()
    for attempt in range(max_swipes + 1):
        found = driver.execute_script(
            js + "return !!findBankInput(arguments[0]);", label_keyword
        )
        if found:
            driver.execute_script(
                js
                + """
                const inp = findBankInput(arguments[0]);
                if (inp) inp.scrollIntoView({block: 'center', behavior: 'instant'});
                const row = getBankFieldRow(arguments[0]);
                if (row) row.scrollIntoView({block: 'center', behavior: 'instant'});
                """,
                label_keyword,
            )
            time.sleep(0.4)
            return True
        if attempt < max_swipes:
            swipe_up_h5(driver, distance=280)
    return False


def normalize_bank_field_value(raw):
    """处理重复输入（如 12345678901234567890 → 1234567890）"""
    val = (raw or "").strip()
    if len(val) >= 2 and len(val) % 2 == 0:
        half = len(val) // 2
        if val[:half] == val[half:]:
            return val[:half]
    return val


def h5_get_bank_field_value(driver, label_keyword):
    raw = driver.execute_script(
        _h5_bank_field_js() + "return getBankFieldValue(arguments[0]);",
        label_keyword,
    ) or ""
    return normalize_bank_field_value(raw)


def h5_fill_bank_field(driver, label_keyword, value, max_swipes=10):
    """填写绑卡字段，支持滑动查找；只填一次，避免重复输入"""
    value = str(value).strip()
    current = h5_get_bank_field_value(driver, label_keyword)
    if current == value:
        print(f"⏭️ {label_keyword} 已有: {value}")
        return True

    if not h5_scroll_up_find_bank_field(driver, label_keyword, max_swipes=max_swipes):
        print(f"⚠️ 滑动后仍未找到字段: {label_keyword}")
        return False

    js = _h5_bank_field_js()
    if current and current != value:
        driver.execute_script(js + "return clearBankField(arguments[0]);", label_keyword)
        time.sleep(0.2)

    driver.execute_script(
        js + "return fillBankField(arguments[0], arguments[1]);",
        label_keyword,
        value,
    )
    time.sleep(0.3)
    after = h5_get_bank_field_value(driver, label_keyword)
    if after == value:
        print(f"✅ {label_keyword} 已填: {value}")
        return True

    driver.execute_script(js + "return clearBankField(arguments[0]);", label_keyword)
    time.sleep(0.2)
    try:
        inp = driver.execute_script(js + "return findBankInput(arguments[0]);", label_keyword)
        if inp:
            inp.clear()
            inp.send_keys(value)
            time.sleep(0.3)
            after = normalize_bank_field_value(inp.get_attribute("value") or "")
            if after == value:
                print(f"✅ {label_keyword} 已填: {value}")
                return True
    except Exception:
        pass

    h5_hide_keyboard(driver)
    after = h5_get_bank_field_value(driver, label_keyword)
    if after == value:
        print(f"✅ {label_keyword} 已填: {value}")
        return True

    print(f"⚠️ {label_keyword} 填写失败，当前值: {after or '(空)'}")
    return False


def h5_bank_form_ready(driver, ifsc, account_no, account_confirm):
    """绑卡三项均已填写"""
    ifsc_ok = h5_get_bank_field_value(driver, "IFSC code") == ifsc
    acct_ok = h5_get_bank_field_value(driver, "Account No.") == account_no
    confirm_ok = (
        h5_get_bank_field_value(driver, "Account No. confirmation") == account_confirm
    )
    if not ifsc_ok:
        print(f"⚠️ IFSC 未完成: {h5_get_bank_field_value(driver, 'IFSC code') or '(空)'}")
    if not acct_ok:
        print(f"⚠️ Account No. 未完成: {h5_get_bank_field_value(driver, 'Account No.') or '(空)'}")
    if not confirm_ok:
        print(
            f"⚠️ Account No. confirmation 未完成: "
            f"{h5_get_bank_field_value(driver, 'Account No. confirmation') or '(空)'}"
        )
    return ifsc_ok and acct_ok and confirm_ok


def fill_kyc_bank_account_form(
    driver,
    ifsc=None,
    account_no=None,
    account_confirm=None,
    max_swipes=10,
):
    """
    KYC 绑卡页面（Bank information）
    IFSC → Account No. → Account No. confirmation → Next
    """
    print("=== 开始填写 KYC 绑卡页面 ===")

    ifsc = (ifsc or KYC_BANK_TEST_DATA["ifsc"]).strip().upper()
    account_no = (account_no or KYC_BANK_TEST_DATA["account_no"]).strip()
    account_confirm = (
        account_confirm or KYC_BANK_TEST_DATA["account_confirm"]
    ).strip()

    ensure_bank_webview(driver, timeout=20)
    if not wait_for_h5_text(driver, "Bank information", timeout=30):
        if not wait_for_h5_text(driver, "Bank Account", timeout=10):
            driver.save_screenshot("kyc_bank_page_not_found.png")
            raise TimeoutException("未进入 Bank information 页面")

    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.8)
    driver.save_screenshot("kyc_bank_step0_entry.png")
    print("✅ 已进入 Bank information 页面")

    fields = (
        ("IFSC code", ifsc),
        ("Account No.", account_no),
        ("Account No. confirmation", account_confirm),
    )
    for label, val in fields:
        if not h5_fill_bank_field(driver, label, val, max_swipes=max_swipes):
            safe_name = label.replace(" ", "_").replace(".", "")
            driver.save_screenshot(f"kyc_bank_fill_fail_{safe_name}.png")
            raise TimeoutException(f"未能填写 {label}")

    h5_hide_keyboard(driver)
    driver.execute_script(_h5_bank_field_js() + "return ensureBankCheckboxChecked();")
    time.sleep(0.5)

    if not h5_bank_form_ready(driver, ifsc, account_no, account_confirm):
        driver.save_screenshot("kyc_bank_incomplete.png")
        raise TimeoutException("绑卡表单未填写完整")

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(0.5)
    if not h5_click_bottom_button(driver, "Next", timeout=15):
        h5_click_form_next(driver)

    time.sleep(2)
    driver.save_screenshot("kyc_bank_after_next.png")
    print("✅ KYC 绑卡页面提交完成")
    return True

