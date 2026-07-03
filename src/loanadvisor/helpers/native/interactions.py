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

def swipe_up(driver):
    """
    页面上滑
    """
    size = driver.get_window_size()

    x = size["width"] // 2

    start_y = int(size["height"] * 0.8)

    end_y = int(size["height"] * 0.3)

    driver.swipe(
        x,
        start_y,
        x,
        end_y,
        500
    )

    print("执行上滑")


_KEYBOARD_BACK_TEXTS = ("Back", "返回", "Done", "完成", "收起")


def _is_keyboard_shown(driver) -> bool:
    try:
        return driver.is_keyboard_shown()
    except Exception:
        return True


def _click_keyboard_back(driver) -> bool:
    for text in _KEYBOARD_BACK_TEXTS:
        try:
            btn = driver.find_element(
                AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiSelector().text("{text}")',
            )
            btn.click()
            time.sleep(0.3)
            return True
        except Exception:
            pass
    return False


def hide_keyboard_native(driver, anchor_texts=()):
    """收起原生软键盘（仅 API / 键盘 Back）。登录弹窗场景请用坐标点击，勿调用本方法。"""
    if not _is_keyboard_shown(driver):
        return False

    try:
        driver.hide_keyboard()
        time.sleep(0.35)
        if not _is_keyboard_shown(driver):
            return True
    except Exception:
        pass

    if _click_keyboard_back(driver) and not _is_keyboard_shown(driver):
        return True

    return not _is_keyboard_shown(driver)


def _click_at_element_center(driver, by, value):
    """按元素中心坐标点击，键盘打开时也不收键盘，避免误关登录弹窗"""
    element = driver.find_element(by, value)
    rect = element.rect
    x = int(rect["x"] + rect["width"] / 2)
    y = int(rect["y"] + rect["height"] / 2)
    print(f"坐标点击: ({x}, {y}) {value}")
    try:
        driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
    except Exception:
        driver.tap([(x, y)], 200)
    time.sleep(0.2)


def _perform_click(driver, by, value, element):
    """键盘遮挡时用坐标点击；不收键盘，防止登录弹窗被遮罩关闭"""
    if _is_keyboard_shown(driver):
        _click_at_element_center(driver, by, value)
        return

    try:
        element.click()
    except StaleElementReferenceException:
        _click_at_element_center(driver, by, value)
    except Exception:
        _click_at_element_center(driver, by, value)


def find_element_smart(driver, by, value, timeout=20, max_swipes=5):
    """
    1. 低频弹窗处理
    2. 查找元素
    3. 连续失败则 swipe（不在此处收键盘，避免关闭登录弹窗）
    """
    end_time = time.time() + timeout
    swipe_count = 0
    fail_count = 0
    last_popup_check = 0

    while time.time() < end_time:

        if time.time() - last_popup_check > 3:
            handle_permission_popup(driver)
            last_popup_check = time.time()

        try:
            element = driver.find_element(by, value)
            return element

        except Exception:
            fail_count += 1

        if fail_count >= 2 and swipe_count < max_swipes:
            swipe_up(driver)
            swipe_count += 1
            fail_count = 0

        time.sleep(0.2)

    raise TimeoutException(f"未找到元素: {value}")


def smart_click(
        driver,
        by,
        value,
        timeout=2,
        max_swipes=5
):
    element = find_element_smart(
        driver,
        by,
        value,
        timeout,
        max_swipes
    )

    _perform_click(driver, by, value, element)

    print(f"点击成功: {value}")


def smart_input(
        driver,
        by,
        value,
        text,
        timeout=2
):
    element = find_element_smart(
        driver,
        by,
        value,
        timeout
    )

    element.clear()

    element.send_keys(text)

    print(f"输入成功: {text}")


# =====================
# 3. 原生登录操作（示例，需你用Inspector改定位）
# =====================
# # 同意通知权限
# allow_notification_btn = driver.find_element("id", "android:id/button1")
# allow_notification_btn.click()
#
# # 点击同意并继续
# btn_agree = driver.find_element(
#     AppiumBy.ANDROID_UIAUTOMATOR,
#     'new UiSelector().text("Agree & Continue")'
# )
# btn_agree.click()

smart_click(
    driver,
    AppiumBy.ANDROID_UIAUTOMATOR,
    'new UiSelector().text("Agree & Continue")',
    timeout=10,
)

# 点击同意权限
smart_click(
    driver,
    AppiumBy.ANDROID_UIAUTOMATOR,
    'new UiSelector().className("android.view.View").instance(12)',
    timeout=10,
)
# btn_agree_TP = driver.find_element(
#     AppiumBy.ANDROID_UIAUTOMATOR,
#     'new UiSelector().className("android.view.View").instance(12)'
# )
# btn_agree_TP.click()

# 示例：点击登录按钮

smart_click(
    driver,
    AppiumBy.ANDROID_UIAUTOMATOR,
    'new UiSelector().text("Login with Mobile Number")',
    timeout=10,
)
# login_btn = driver.find_element(
#     AppiumBy.ANDROID_UIAUTOMATOR,
#     'new UiSelector().text("Login with Mobile Number")'
# )
# login_btn.click()
# 点击手机号输入框
# smart_click(
#     driver,
#     AppiumBy.ANDROID_UIAUTOMATOR,
#     'new UiSelector().text("Enter mobile number")'
# )
# login_btn_ph = driver.find_element(
#     AppiumBy.ANDROID_UIAUTOMATOR,
#     'new UiSelector().text("Enter mobile number")'
# )
# login_btn_ph.click()

# 输入手机号
# phone_input = driver.find_element(
#     AppiumBy.CLASS_NAME,
#     'android.widget.EditText'
# )
# phone_input.send_keys("9110001237")
hide_keyboard_native(driver)

smart_input(
    driver,
    AppiumBy.CLASS_NAME,
    'android.widget.EditText',
    TEST_MOBILE,
    timeout=10,
)

hide_keyboard_native(driver)

smart_click(
    driver,
    AppiumBy.ANDROID_UIAUTOMATOR,
    'new UiSelector().text("Send OTP")',
    timeout=10,
)
# phone_sendotp = driver.find_element(
#     AppiumBy.XPATH,
#     '//android.widget.TextView[@text="Send OTP"]'
# )
# phone_sendotp.click()

# 等待 OTP 弹窗
smart_input(
    driver,
    AppiumBy.CLASS_NAME,
    'android.widget.EditText',
    TEST_OTP,
    timeout=10,
)
# otp_input = WebDriverWait(driver, 10).until(
#     EC.element_to_be_clickable(
#         (AppiumBy.CLASS_NAME, "android.widget.EditText")
#     )
# )
#
# print("OTP页面加载成功")
# otp_input.send_keys("123456")

# 点击提交
# hide_keyboard_native(driver)
smart_click(
    driver,
    AppiumBy.ANDROID_UIAUTOMATOR,
    'new UiSelector().text("Verify & Login")',
    timeout=10,
)
# phone_login = driver.find_element(
#     AppiumBy.XPATH,
#     '//android.widget.TextView[@text="Verify & Login"]'
# )
# phone_login.click()

print("登录流程完成")


# =====================
# 5. 切换到H5(WebView)（修复版）
# =====================
