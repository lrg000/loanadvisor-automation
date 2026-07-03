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

from loanadvisor.helpers.kyc.confirm_modal import (
    _h5_click_date_picker_confirm,
    _h5_is_date_picker_open,
    h5_fill_kyc_confirm_form,
    h5_kyc_confirm_form_likely_ready,
)
from loanadvisor.helpers.kyc.shared import (
    KYC_OCR_TEST_DATA,
    _h5_aadhaar_ocr_preview_ready,
    _kyc_navigate_to_aadhaar_upload,
    _kyc_trigger_camera_allow,
    _native_complete_photo_selection,
    _wait_for_aadhaar_photo_ready,
    ensure_kyc_webview,
    generate_valid_pan,
    h5_wait_and_click_submit,
    is_valid_pan,
)
from loanadvisor.helpers.native.permissions import handle_permission_popup
from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import h5_click_bottom_button, h5_click_form_next, h5_click_modal_button
from loanadvisor.helpers.webview.switcher import switch_to_real_webview

def fill_kyc_aadhaar_ocr(
    driver,
    full_name=None,
    date_of_birth=None,
    pan_number=None,
    prefer_files=True,
):
    """
    KYC 身份验证 OCR 流程（Aadhaar 正面）
    Identity Verification → Next → Next → Allow → 拍照/选图 → Submit → 确认信息 → Next

    拍照/选图失败时进入人工等待（默认最多 300 秒，可通过 KYC_PHOTO_MANUAL_WAIT_SEC 调整），
    检测到预览页 Submit 后自动继续后续 Submit 与表单填写。
    """
    print("=== 开始 KYC Aadhaar OCR 身份验证 ===")

    ensure_kyc_webview(driver, timeout=20)
    driver.save_screenshot("kyc_step0_entry.png")

    if not _kyc_navigate_to_aadhaar_upload(driver):
        driver.save_screenshot("kyc_navigate_fail.png")
        raise TimeoutException("未能进入 Front of Aadhaar 页面")

    driver.save_screenshot("kyc_step1_front_aadhaar.png")

    if not _kyc_trigger_camera_allow(driver):
        print("⚠️ 未检测到 Allow Camera Access，尝试继续...")

    if wait_for_h5_text(driver, "Allow Camera Access", timeout=5):
        h5_click_modal_button(driver, "Allow", timeout=10)
        time.sleep(1.0)

    handle_permission_popup(driver, timeout=8)

    manual_wait_sec = settings.kyc_photo_manual_wait_sec
    if _h5_aadhaar_ocr_preview_ready(driver):
        print("⏭️ 已在 Aadhaar 预览页，跳过拍照/选图")
    else:
        photo_ok = _native_complete_photo_selection(
            driver, prefer_files=prefer_files
        )
        if not photo_ok:
            driver.save_screenshot("kyc_photo_fail.png")
            print("⚠️ 自动拍照/选图失败，进入人工等待模式...")
            photo_ok = _wait_for_aadhaar_photo_ready(
                driver, timeout=manual_wait_sec, manual_hint=True
            )
        if not photo_ok:
            driver.save_screenshot("kyc_photo_manual_timeout.png")
            raise TimeoutException(
                "拍照/选图失败（自动操作与人工等待均未完成）"
            )

    ensure_kyc_webview(driver, timeout=15)
    driver.save_screenshot("kyc_step2_preview.png")

    if not h5_wait_and_click_submit(driver, timeout=45):
        raise TimeoutException("未能点击 Submit 进行 OCR")

    ensure_kyc_webview(driver, timeout=15)
    driver.save_screenshot("kyc_step3_ocr_confirm.png")

    date_of_birth = date_of_birth or KYC_OCR_TEST_DATA["date_of_birth"]
    pan_number = (pan_number or KYC_OCR_TEST_DATA["pan_number"]).strip().upper()
    if not is_valid_pan(pan_number):
        pan_number = generate_valid_pan()

    form_ok = h5_fill_kyc_confirm_form(
        driver,
        full_name=full_name,
        date_of_birth=date_of_birth,
        pan_number=pan_number,
    )
    if not form_ok:
        likely, info = h5_kyc_confirm_form_likely_ready(
            driver, pan_number, date_of_birth
        )
        if likely:
            print(
                f"⚠️ 表单检测存在误差，界面已填写 "
                f"DOB={info.get('dob')} PAN={info.get('pan')}，继续点击 Next"
            )
            form_ok = True
        else:
            raise TimeoutException(
                "KYC Confirm your info 未完成：Date of Birth 或 PAN card number 未填好"
            )

    if _h5_is_date_picker_open(driver):
        _h5_click_date_picker_confirm(driver, dob=date_of_birth)
        time.sleep(0.6)

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(0.6)
    if not h5_click_bottom_button(driver, "Next", timeout=15):
        h5_click_form_next(driver)

    time.sleep(2)
    driver.save_screenshot("kyc_step4_after_next.png")
    print("✅ KYC Aadhaar OCR 身份验证完成")
