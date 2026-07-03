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

from loanadvisor.helpers.native.permissions import handle_permission_popup
from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import h5_click_bottom_button, h5_click_modal_button
from loanadvisor.helpers.webview.switcher import switch_to_real_webview

KYC_OCR_TEST_DATA = {
    "full_name": settings.kyc_ocr_full_name,
    "date_of_birth": settings.kyc_ocr_dob,
    "pan_number": settings.kyc_ocr_pan,
}

KYC_BANK_TEST_DATA = {
    "ifsc": settings.kyc_bank_ifsc,
    "account_no": settings.kyc_bank_account,
    "account_confirm": settings.kyc_bank_account,
}


def generate_valid_pan():
    """生成符合规则的 PAN：5 字母 + 4 数字 + 1 字母"""
    letters = string.ascii_uppercase
    digits = string.digits
    return (
        "".join(random.choices(letters, k=5))
        + "".join(random.choices(digits, k=4))
        + random.choice(letters)
    )


def is_valid_pan(pan):
    """PAN 格式：ABCDE1234F"""
    if not pan:
        return False
    pan = pan.strip().upper()
    if len(pan) != 10:
        return False
    return (
        pan[:5].isalpha()
        and pan[5:9].isdigit()
        and pan[9].isalpha()
    )


def normalize_pan_value(raw):
    """从 input 值提取合法 PAN（处理重复输入 ABCDE1234FABCDE1234F）"""
    val = (raw or "").strip().upper()
    if is_valid_pan(val):
        return val
    if len(val) == 20 and val[:10] == val[10:] and is_valid_pan(val[:10]):
        return val[:10]
    if len(val) > 10 and is_valid_pan(val[:10]):
        return val[:10]
    return val


def ensure_kyc_webview(driver, timeout=15):
    """切换到 KYC / Identity Verification WebView"""
    for keyword in ("identity", "KYCProcess", "emergencyContacts"):
        try:
            switch_to_real_webview(driver, keyword=keyword, timeout=max(5, timeout // 3))
            time.sleep(0.8)
            return
        except Exception:
            pass
    switch_to_real_webview(driver, timeout=timeout)
    time.sleep(0.8)


def h5_get_field_value(driver, label_keyword):
    """读取 H5 表单字段当前值"""
    return driver.execute_script(
        h5_get_field_container_js()
        + """
        const label = arguments[0];
        const row = getFieldRow(label);
        if (!row) return '';
        const inp = row.querySelector('input, textarea');
        if (inp) return (inp.value || '').trim();
        const lines = (row.innerText || '').trim().split('\\n').map(s => s.trim()).filter(Boolean);
        for (const line of lines) {
            const l = line.toLowerCase();
            if (l === label.toLowerCase()) continue;
            if (l.startsWith('select ')) continue;
            if (line.length >= 2) return line;
        }
        return '';
        """,
        label_keyword,
    ) or ""


def h5_click_modal_button(driver, text, timeout=12):
    """点击弹窗/底部 sheet 内按钮（Allow、Submit 等）"""
    end_time = time.time() + timeout
    while time.time() < end_time:
        if h5_click_text_and_parents(driver, text, timeout=2):
            print(f"✅ 已点击弹窗按钮: {text}")
            return True
        clicked = driver.execute_script(
            """
            const wanted = (arguments[0] || '').trim();
            for (const el of document.querySelectorAll('button, a, div, span, p')) {
                const t = (el.innerText || '').trim();
                if (t !== wanted) continue;
                const r = el.getBoundingClientRect();
                if (r.width < 40 || r.height < 16) continue;
                el.scrollIntoView({block: 'center', behavior: 'instant'});
                el.click();
                return true;
            }
            return false;
            """,
            text,
        )
        if clicked:
            print(f"✅ 已点击弹窗按钮(JS): {text}")
            return True
        time.sleep(0.5)
    print(f"⚠️ 未找到弹窗按钮: {text}")
    return False


def _kyc_navigate_to_aadhaar_upload(driver):
    """Identity Verification → Next → Next / 上传入口 → Front of Aadhaar"""
    wait_for_h5_text(driver, "Identity Verification", timeout=20)
    time.sleep(0.8)

    if wait_for_h5_text(driver, "Front of Aadhaar", timeout=2):
        return True

    h5_click_bottom_button(driver, "Next", timeout=10)
    time.sleep(1.2)

    if wait_for_h5_text(driver, "Front of Aadhaar", timeout=5):
        return True

    click_any_target_text(
        driver,
        ["Upload Aadhaar card front photo", "Upload Aadhaar"],
        timeout=4,
    )
    time.sleep(1.0)

    if wait_for_h5_text(driver, "Front of Aadhaar", timeout=8):
        return True

    h5_click_bottom_button(driver, "Next", timeout=10)
    time.sleep(1.2)

    return wait_for_h5_text(driver, "Front of Aadhaar", timeout=10) or wait_for_h5_text(
        driver, "Allow Camera Access", timeout=5
    )


def _kyc_trigger_camera_allow(driver):
    """Front of Aadhaar 页触发 Allow Camera Access 弹窗"""
    if wait_for_h5_text(driver, "Allow Camera Access", timeout=2):
        return True

    h5_click_bottom_button(driver, "Next", timeout=6)
    time.sleep(1.0)
    if wait_for_h5_text(driver, "Allow Camera Access", timeout=5):
        return True

    driver.execute_script(
        """
        for (const el of document.querySelectorAll('div, span, p, img, button')) {
            const t = (el.innerText || '').toLowerCase();
            if (t.includes('take a photo') || t.includes('good example')
                || t.includes('front of aadhaar')) {
                el.scrollIntoView({block: 'center', behavior: 'instant'});
                el.click();
                return true;
            }
        }
        return false;
        """
    )
    time.sleep(0.8)
    return wait_for_h5_text(driver, "Allow Camera Access", timeout=8)


def _native_choose_photo_source(driver, source="Files", timeout=12):
    """原生底部 sheet：Camera / Files"""
    end_time = time.time() + timeout
    labels = [source] if source else ["Files", "Camera"]
    while time.time() < end_time:
        try:
            driver.switch_to.context("NATIVE_APP")
            for label in labels:
                for el in driver.find_elements(
                    AppiumBy.XPATH, f"//*[@text='{label}']"
                ):
                    if el.is_displayed():
                        el.click()
                        print(f"✅ 已选择照片来源: {label}")
                        time.sleep(1.0)
                        return label
        except Exception:
            pass
        time.sleep(0.4)
    print("⚠️ 未找到 Camera/Files 选项")
    return None


def _native_take_camera_photo(driver, timeout=15):
    """原生相机：快门 + 确认"""
    handle_permission_popup(driver, timeout=5)
    end_time = time.time() + timeout
    shutter_ids = [
        "com.android.camera:id/shutter_button",
        "com.android.camera2:id/shutter_button",
        "com.sec.android.app.camera:id/shutter",
        "com.huawei.camera:id/shutter_button",
        "com.oplus.camera:id/shutter_button",
    ]
    while time.time() < end_time:
        try:
            driver.switch_to.context("NATIVE_APP")
            for rid in shutter_ids:
                for el in driver.find_elements(AppiumBy.ID, rid):
                    if el.is_displayed():
                        el.click()
                        print("✅ 已点击相机快门")
                        time.sleep(1.5)
                        if _native_confirm_camera_photo(driver):
                            return True
            for desc in ("Shutter", "Take photo", "Capture"):
                for el in driver.find_elements(
                    AppiumBy.XPATH, f"//*[contains(@content-desc,'{desc}')]"
                ):
                    if el.is_displayed():
                        el.click()
                        time.sleep(1.5)
                        if _native_confirm_camera_photo(driver):
                            return True
        except Exception:
            pass
        time.sleep(0.5)

    try:
        size = driver.get_window_size()
        driver.tap([(size["width"] // 2, int(size["height"] * 0.92))], 300)
        time.sleep(1.5)
        return _native_confirm_camera_photo(driver)
    except Exception:
        return False


def _native_confirm_camera_photo(driver, timeout=8):
    """相机拍完后点 Done / OK / 对勾"""
    end_time = time.time() + timeout
    confirm_texts = ("Done", "OK", "Save", "Confirm", "Tick", "✓")
    while time.time() < end_time:
        try:
            driver.switch_to.context("NATIVE_APP")
            for txt in confirm_texts:
                for el in driver.find_elements(
                    AppiumBy.XPATH,
                    f"//*[contains(@text,'{txt}') or contains(@content-desc,'{txt}')]",
                ):
                    if el.is_displayed():
                        el.click()
                        print(f"✅ 相机照片已确认: {txt}")
                        time.sleep(1.0)
                        return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def _native_pick_gallery_photo(driver, index=0, timeout=18):
    """相册/Files：选第 index 张图片"""
    handle_permission_popup(driver, timeout=4)
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            driver.switch_to.context("NATIVE_APP")
            for rv_class in (
                "androidx.recyclerview.widget.RecyclerView",
                "android.widget.GridView",
                "android.widget.ListView",
            ):
                for lst in driver.find_elements(AppiumBy.CLASS_NAME, rv_class):
                    if not lst.is_displayed():
                        continue
                    items = lst.find_elements(AppiumBy.XPATH, "./*")
                    if len(items) > index:
                        items[index].click()
                        print(f"✅ 已从相册选择第 {index + 1} 张照片")
                        time.sleep(1.2)
                        return True
            imgs = [
                e
                for e in driver.find_elements(
                    AppiumBy.CLASS_NAME, "android.widget.ImageView"
                )
                if e.is_displayed() and e.size.get("width", 0) > 80
            ]
            if imgs:
                imgs[min(index, len(imgs) - 1)].click()
                print(f"✅ 已从 ImageView 选择第 {index + 1} 张照片")
                time.sleep(1.2)
                return True
        except Exception:
            pass
        time.sleep(0.5)
    print("⚠️ 未能从相册选择照片")
    return False


def _native_complete_photo_selection(driver, prefer_files=True):
    """Allow 后选择 Camera 或 Files 并完成选图/拍照"""
    source = _native_choose_photo_source(
        driver, source="Files" if prefer_files else "Camera", timeout=12
    )
    if not source:
        source = _native_choose_photo_source(driver, source=None, timeout=6)
    if not source:
        return False

    handle_permission_popup(driver, timeout=5)
    if source == "Camera":
        return _native_take_camera_photo(driver, timeout=18)
    return _native_pick_gallery_photo(driver, index=0, timeout=18)


def _h5_aadhaar_ocr_preview_ready(driver):
    """Aadhaar OCR 拍照/选图完成后的 H5 预览页（可见 Submit）"""
    try:
        ensure_kyc_webview(driver, timeout=5)
        return bool(
            driver.execute_script(
                """
                const body = document.body.innerText || '';
                if (!body.includes('Submit')) return false;
                if (body.includes('Allow Camera Access') && !body.includes('Retake')) {
                    return false;
                }
                for (const el of document.querySelectorAll('button, [role=button], div, span, a')) {
                    const t = (el.innerText || '').trim();
                    if (t !== 'Submit') continue;
                    const r = el.getBoundingClientRect();
                    if (r.width > 40 && r.height > 18 && r.top >= 0 && r.top < innerHeight) {
                        return true;
                    }
                }
                return false;
                """
            )
        )
    except Exception:
        return False


def _wait_for_aadhaar_photo_ready(driver, timeout=300, poll_interval=2.0, manual_hint=True):
    """
    等待 Aadhaar 拍照/选图完成（自动失败后的人工兜底）。
    成功条件：回到 WebView 且预览页 Submit 可见。
    """
    if _h5_aadhaar_ocr_preview_ready(driver):
        print("✅ 已在 Aadhaar 预览页")
        return True

    if manual_hint:
        print(
            "⚠️ 自动拍照/选图未完成，请在手机上人工完成拍照或从相册选图。"
            f"脚本将等待最多 {int(timeout)} 秒，完成后自动继续 Submit..."
        )
        driver.save_screenshot("kyc_photo_manual_wait.png")

    end_time = time.time() + timeout
    last_log = 0.0
    while time.time() < end_time:
        handle_permission_popup(driver, timeout=1)

        if _h5_aadhaar_ocr_preview_ready(driver):
            print("✅ 检测到预览页 Submit，拍照/选图已完成（含人工操作）")
            return True

        now = time.time()
        if now - last_log >= 15:
            remaining = max(0, int(end_time - now))
            print(f"⏳ 等待人工完成拍照/选图... 剩余约 {remaining} 秒")
            last_log = now

        time.sleep(poll_interval)

    return False


def h5_wait_and_click_submit(driver, timeout=45):
    """等待 OCR 预览页 Submit 按钮并点击"""
    ensure_kyc_webview(driver, timeout=10)
    end_time = time.time() + timeout
    while time.time() < end_time:
        if wait_for_h5_text(driver, "Submit", timeout=2):
            if h5_click_bottom_button(driver, "Submit", timeout=5):
                time.sleep(2)
                return True
        if h5_click_bottom_button(driver, "Submit", timeout=2):
            time.sleep(2)
            return True
        time.sleep(0.8)
    driver.save_screenshot("kyc_submit_not_found.png")
    print("⚠️ 未找到 Submit 按钮")
    return False

