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

def handle_permission_popup(driver, timeout=8):
    """
    Android 通用权限弹窗处理

    返回:
        True  : 处理了权限
        False : 没发现权限
    """

    current_context = driver.current_context

    try:

        # 如果当前是WEBVIEW，先切回Native
        if current_context != "NATIVE_APP":
            driver.switch_to.context("NATIVE_APP")

        end_time = time.time() + timeout

        handled = False

        while time.time() < end_time:

            # ==========================
            # 第一优先：直接找系统按钮ID
            # ==========================

            allow_ids = [

                # Android 11+
                "com.android.permissioncontroller:id/permission_allow_button",

                "com.android.permissioncontroller:id/permission_allow_foreground_only_button",

                "com.android.permissioncontroller:id/permission_allow_one_time_button",

                # Android 9/10
                "com.android.packageinstaller:id/permission_allow_button",

                # 通用
                "android:id/button1",

                # MIUI
                "com.lbe.security.miui:id/permission_allow_button",

                # OPPO
                "com.coloros.securitypermission:id/permission_allow_button",

                # vivo
                "com.vivo.permissionmanager:id/permission_allow_button",

            ]

            clicked = False

            for rid in allow_ids:

                buttons = driver.find_elements(AppiumBy.ID, rid)

                for btn in buttons:

                    if not btn.is_displayed():
                        continue

                    if not btn.is_enabled():
                        continue

                    print(
                        f"点击权限按钮(ID): {btn.text}  {rid}"
                    )

                    btn.click()

                    handled = True
                    clicked = True

                    time.sleep(1)

                    break

                if clicked:
                    break

            if clicked:
                continue

            # ==========================
            # 第二优先：扫描所有Button
            # ==========================

            buttons = driver.find_elements(
                AppiumBy.CLASS_NAME,
                "android.widget.Button"
            )

            allow_texts = [

                "allow",
                "always allow",
                "while using the app",
                "only this time",

                "允许",
                "始终允许",
                "仅使用期间允许",
                "使用应用期间",
                "本次允许",

                "ok",
                "确定",
            ]

            for btn in buttons:

                if not btn.is_displayed():
                    continue

                text = (btn.text or "").strip().lower()

                if not text:
                    continue

                if any(x.lower() == text for x in allow_texts):

                    print(
                        f"点击权限按钮(Text): {btn.text}"
                    )

                    btn.click()

                    handled = True

                    clicked = True

                    time.sleep(1)

                    break

            if clicked:
                continue

            # ==========================
            # 判断是否还有权限页面
            # ==========================

            page = driver.page_source.lower()

            permission_keywords = [

                "permission",
                "allow",
                "位置",
                "定位",
                "camera",
                "microphone",
                "notification",
                "storage",
                "照片",
                "相机",
                "通知",
                "麦克风"

            ]

            if not any(k in page for k in permission_keywords):
                break

            time.sleep(0.5)

        return handled

    finally:

        if driver.current_context != current_context:

            try:
                driver.switch_to.context(current_context)
            except:
                pass


import time


def handle_all_permission_popups(
        driver,
        timeout=8,
        interval=0.5
):
    end_time = time.time() + timeout

    count = 0
    miss_count = 0

    while time.time() < end_time:

        handled = handle_permission_popup(driver)

        if handled:
            count += 1
            miss_count = 0

            time.sleep(1)
            continue

        miss_count += 1

        # 连续2次没发现弹窗直接结束
        if miss_count >= 2:
            break

        time.sleep(interval)

    print(f"权限弹窗处理完成，共处理 {count} 个")

    return count


