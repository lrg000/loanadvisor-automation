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

def enable_usage_access(driver, app_name=None):
    """
    打开 Usage Access（Android 使用情况访问权限）
    """

    print("进入 Usage Access 开关处理...")

    time.sleep(2)

    # ========== 1. 找开关（优先 Switch） ==========
    switches = driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.Switch")

    if switches:
        for sw in switches:
            try:
                state = sw.get_attribute("checked")
                print("Switch状态:", state)

                if state == "false":
                    sw.click()
                    print("已点击 Switch 打开权限")
                    return True
                else:
                    print("Switch 已开启")
                    return True
            except:
                continue

    # ========== 2. 找整行 clickable（更常见） ==========
    rows = driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.LinearLayout")

    for row in rows:
        try:
            if row.is_displayed() and row.is_enabled():
                row.click()
                print("点击 row 进入详情页")

                time.sleep(1)

                # 再找 switch
                sw2 = driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.Switch")
                for s in sw2:
                    try:
                        if s.get_attribute("checked") == "false":
                            s.click()
                            print("详情页打开 switch 成功")
                            return True
                    except:
                        pass

        except:
            pass

    print("未找到可用 Usage Access 开关")
    return False


def handle_app_usage_settings(driver, timeout=10):
    """
    处理 AppUsage / Usage access 设置弹窗：
    1. 点击 Settings
    2. 打开开关
    3. 返回 App
    """

    current_context = driver.current_context

    try:
        if current_context != "NATIVE_APP":
            driver.switch_to.context("NATIVE_APP")

        print("检查 AppUsage 设置弹窗...")

        # ========== Step 1: 点击 Settings ==========
        settings_locators = [
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("Settings")'),
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("SETTING")'),
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("设置")'),
            (By.ID, "android:id/button1"),
        ]

        settings_clicked = False

        for by, value in settings_locators:
            try:
                el = driver.find_element(by, value)
                if el.is_displayed():
                    el.click()
                    print("已点击 Settings / 设置入口")
                    settings_clicked = True
                    time.sleep(2)
                    break
            except:
                pass

        if not settings_clicked:
            print("未检测到 Settings 弹窗")
            return False

        enable_usage_access(driver)

        # ========== Step 3: 返回 App ==========
        driver.back()
        time.sleep(1)

        print("已返回 App")
        return True

    finally:
        if driver.current_context != current_context:
            driver.switch_to.context(current_context)


def _browser_chooser_visible(driver):
    """检测系统「选择浏览器打开」弹窗是否出现"""
    hints = [
        "Chrome", "UC Browser", "360手机助手",
        "Open with", "打开方式", "选择浏览器", "Choose",
    ]
    for hint in hints:
        try:
            el = driver.find_element(
                AppiumBy.ANDROID_UIAUTOMATOR,
                f'new UiSelector().textContains("{hint}")',
            )
            if el.is_displayed():
                return True
        except Exception:
            pass
    return False


def handle_browser_chooser_if_present(
        driver,
        timeout=6,
        preferred_browsers=("Chrome", "Google Chrome", "UC Browser", "Browser", "浏览器"),
):
    """
    可选处理：Repay 后系统「选择浏览器打开」弹窗（部分手机会出现，非必须）
    检测到则点击首选浏览器；未检测到则静默跳过。
    """
    current_context = driver.current_context
    end_time = time.time() + timeout
    handled = False
    miss_count = 0

    browser_locators = []
    for name in preferred_browsers:
        browser_locators.append((
            AppiumBy.ANDROID_UIAUTOMATOR,
            f'new UiSelector().text("{name}")',
        ))
        browser_locators.append((
            AppiumBy.ANDROID_UIAUTOMATOR,
            f'new UiSelector().textContains("{name}")',
        ))
        browser_locators.append((
            AppiumBy.ANDROID_UIAUTOMATOR,
            f'new UiSelector().descriptionContains("{name}")',
        ))

    once_locators = [
        (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("Just once")'),
        (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("Only once")'),
        (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("仅此一次")'),
        (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("仅一次")'),
        (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("Always")'),
        (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("始终")'),
    ]

    try:
        if current_context != "NATIVE_APP":
            driver.switch_to.context("NATIVE_APP")

        print("检查浏览器选择弹窗...")

        while time.time() < end_time:
            if not _browser_chooser_visible(driver):
                miss_count += 1
                if miss_count >= 3:
                    print("ℹ️ 未检测到浏览器选择弹窗，跳过")
                    return False
                time.sleep(0.5)
                continue

            miss_count = 0

            for by, value in browser_locators:
                try:
                    for el in driver.find_elements(by, value):
                        if not el.is_displayed():
                            continue
                        label = (el.text or el.get_attribute("contentDescription") or "").strip()
                        el.click()
                        print(f"✅ 已选择浏览器打开: {label or value}")
                        handled = True
                        time.sleep(1)
                        break
                    if handled:
                        break
                except Exception:
                    pass

            if handled:
                for by, value in once_locators:
                    try:
                        el = driver.find_element(by, value)
                        if el.is_displayed():
                            el.click()
                            print(f"✅ 已确认打开方式: {el.text}")
                            time.sleep(0.8)
                            break
                    except Exception:
                        pass
                driver.save_screenshot("after_browser_chooser.png")
                return True

            time.sleep(0.4)

        print("ℹ️ 浏览器选择弹窗未匹配到可点击项，跳过")
        return False

    finally:
        if driver.current_context != current_context:
            try:
                driver.switch_to.context(current_context)
            except Exception:
                pass

