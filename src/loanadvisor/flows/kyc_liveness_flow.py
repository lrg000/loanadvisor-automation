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

from loanadvisor.helpers.kyc.shared import _native_take_camera_photo, ensure_kyc_webview, h5_wait_and_click_submit
from loanadvisor.helpers.native.permissions import handle_permission_popup
from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import h5_click_bottom_button, h5_click_form_next
from loanadvisor.helpers.webview.switcher import switch_to_real_webview

def _native_in_selfie_camera(driver):
    """检测是否处于原生自拍相机界面"""
    try:
        driver.switch_to.context("NATIVE_APP")
        activity = (driver.current_activity or "").lower()
        if "camera" in activity:
            return True

        shutter_ids = (
            "com.android.camera:id/shutter_button",
            "com.android.camera2:id/shutter_button",
            "com.sec.android.app.camera:id/shutter",
            "com.huawei.camera:id/shutter_button",
            "com.oplus.camera:id/shutter_button",
        )
        for rid in shutter_ids:
            for el in driver.find_elements(AppiumBy.ID, rid):
                if el.is_displayed():
                    return True

        for desc in ("Shutter", "Take photo", "Capture"):
            for el in driver.find_elements(
                AppiumBy.XPATH, f"//*[contains(@content-desc,'{desc}')]"
            ):
                if el.is_displayed():
                    return True

        size = driver.get_window_size()
        for cls in ("android.widget.ImageButton", "android.widget.ImageView"):
            for el in driver.find_elements(AppiumBy.CLASS_NAME, cls):
                if not el.is_displayed():
                    continue
                rect = el.rect
                if rect.get("y", 0) > size["height"] * 0.62 and rect.get("width", 0) > 60:
                    return True
    except Exception:
        pass
    return False


def _h5_selfie_preview_ready(driver):
    """自拍预览页：已拍完，出现 Submit / Retake"""
    try:
        ensure_kyc_webview(driver, timeout=5)
        body = driver.execute_script("return document.body.innerText || ''") or ""
        if "Submit" not in body:
            return False
        if "Retake" in body or "not blurry" in body.lower():
            return True
        if "Upload your selfie" in body and "Identity Verification" in body:
            return True
    except Exception:
        pass
    return False


def _native_wait_selfie_capture_complete(driver, timeout=45):
    """
    等待静默活体拍照完成。
    优先等待自动采集结束并回到 WebView 预览；超时后尝试点击快门。
    """
    handle_permission_popup(driver, timeout=8)
    end_time = time.time() + timeout
    shutter_tried = False

    print("--- 等待静默活体拍照完成 ---")
    while time.time() < end_time:
        handle_permission_popup(driver, timeout=1)

        if _h5_selfie_preview_ready(driver):
            print("✅ 自拍预览页已就绪")
            return True

        if _native_in_selfie_camera(driver):
            elapsed = timeout - (end_time - time.time())
            if elapsed > timeout * 0.45 and not shutter_tried:
                print("--- 静默等待超时，尝试点击相机快门 ---")
                shutter_tried = True
                if _native_take_camera_photo(driver, timeout=12):
                    time.sleep(2.0)
                    continue
                try:
                    driver.switch_to.context("NATIVE_APP")
                    size = driver.get_window_size()
                    driver.tap(
                        [(size["width"] // 2, int(size["height"] * 0.88))], 300
                    )
                    print("✅ 已点击底部快门区域")
                    time.sleep(2.0)
                except Exception:
                    pass
            time.sleep(0.8)
            continue

        try:
            ensure_kyc_webview(driver, timeout=3)
            if wait_for_h5_text(driver, "Submit", timeout=2):
                print("✅ 自拍预览页已就绪(Submit)")
                return True
        except Exception:
            pass

        time.sleep(0.8)

    return _h5_selfie_preview_ready(driver)


def fill_kyc_silent_liveness(driver, photo_wait_timeout=45):
    """
    KYC 静默活体检测
    Upload your selfie 引导页 → Next → 原生相机拍照(等待完成) → Submit
    """
    print("=== 开始 KYC 静默活体检测 ===")

    ensure_kyc_webview(driver, timeout=20)
    driver.save_screenshot("kyc_liveness_step0_entry.png")

    if _h5_selfie_preview_ready(driver):
        print("⏭️ 已在自拍预览页，直接 Submit")
    elif not wait_for_h5_text(driver, "Upload your selfie", timeout=30):
        body = driver.execute_script("return document.body.innerText || ''") or ""
        if "Submit" in body and ("Retake" in body or "not blurry" in body.lower()):
            print("⏭️ 检测到自拍预览页")
        else:
            driver.save_screenshot("kyc_liveness_page_not_found.png")
            raise TimeoutException("未进入 Upload your selfie 页面")
    else:
        print("✅ 已进入 Upload your selfie 引导页")
        driver.save_screenshot("kyc_liveness_step1_guide.png")

        if not h5_click_bottom_button(driver, "Next", timeout=15):
            h5_click_form_next(driver)
        time.sleep(1.0)
        handle_permission_popup(driver, timeout=8)

        if not _native_wait_selfie_capture_complete(
            driver, timeout=photo_wait_timeout
        ):
            driver.save_screenshot("kyc_liveness_photo_fail.png")
            raise TimeoutException("自拍拍照未完成或未回到预览页")

    ensure_kyc_webview(driver, timeout=15)
    driver.save_screenshot("kyc_liveness_step2_preview.png")

    if not h5_wait_and_click_submit(driver, timeout=30):
        if not h5_click_bottom_button(driver, "Submit", timeout=10):
            driver.save_screenshot("kyc_liveness_submit_fail.png")
            raise TimeoutException("未能点击 Submit 完成静默活体检测")

    ensure_kyc_webview(driver, timeout=15)
    time.sleep(2)
    driver.save_screenshot("kyc_liveness_step3_done.png")
    print("✅ KYC 静默活体检测完成")
    return True

