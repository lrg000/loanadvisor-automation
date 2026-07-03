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

from loanadvisor.helpers.native.permissions import handle_all_permission_popups
from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import h5_click_success_confirm
from loanadvisor.helpers.webview.settings import handle_app_usage_settings
from loanadvisor.helpers.webview.switcher import switch_to_real_webview

def run_apply_flow(driver):
    """
    Apply 状态：用户申请新贷款
    权限弹窗 → Usage Access → Success 弹窗 Confirm
    """
    print("=== 执行 Apply 流程 ===")

    time.sleep(2)
    handle_all_permission_popups(driver)
    handle_app_usage_settings(driver)

    try:
        switch_to_real_webview(driver, timeout=15)
    except Exception as e:
        print("WebView 切换跳过:", e)

    wait_for_h5_text(driver, "Success", timeout=20)
    print("当前 context:", driver.current_context)
    driver.save_screenshot("after_apply.png")

    if h5_click_success_confirm(driver, timeout=15):
        time.sleep(2)
    else:
        print("⚠️ Apply 后未能点击 Confirm，请检查页面状态")

    driver.save_screenshot("after_apply_done.png")
    print("✅ Apply 流程完成")
