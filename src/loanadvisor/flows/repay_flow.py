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

from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import (
    h5_click_bottom_button,
    h5_click_repay_loan_button,
    h5_repay_details_visible,
)
from loanadvisor.helpers.webview.settings import handle_browser_chooser_if_present
from loanadvisor.helpers.webview.switcher import switch_to_real_webview

def run_go_to_repay_flow(driver):
    """
    Go to repay 状态：用户有在贷订单
    1. 点击第一个 Repay Loan 进入还款详情
    2. 在 Repayment Details 页点击底部 Repay 按钮
    """
    print("=== 执行 Go to repay 流程 ===")

    time.sleep(3)

    try:
        switch_to_real_webview(driver, timeout=15)
    except Exception as e:
        print("WebView 切换跳过:", e)

    if not wait_for_h5_text(driver, "Repay Loan", timeout=15):
        print("⚠️ 未检测到 Repay Loan，当前页面片段:")
        try:
            print(driver.execute_script("return document.body.innerText.slice(0, 500)"))
        except Exception:
            pass
        driver.save_screenshot("after_repay.png")
        print("✅ Go to repay 流程完成")
        return

    print("✅ 检测到 Repay Loan")
    driver.save_screenshot("before_repay_loan_click.png")

    driver.execute_script(
        """
        for (const el of document.querySelectorAll('button, a, div, span')) {
            if ((el.innerText || '').trim() === 'Repay Loan') {
                el.scrollIntoView({ block: 'center', behavior: 'instant' });
                break;
            }
        }
        """
    )
    time.sleep(0.6)

    if not h5_click_repay_loan_button(driver, timeout=20):
        print("⚠️ 未能点击 Repay Loan")
        driver.save_screenshot("after_repay.png")
        print("✅ Go to repay 流程完成")
        return

    time.sleep(1)

    if not h5_repay_details_visible(driver):
        wait_for_h5_text(driver, "Repayment Details", timeout=5)

    if not h5_repay_details_visible(driver):
        print("⚠️ 未进入 Repayment Details 页面，当前页面片段:")
        try:
            print(driver.execute_script("return document.body.innerText.slice(0, 500)"))
        except Exception:
            pass
        driver.save_screenshot("after_repay.png")
        print("✅ Go to repay 流程完成")
        return

    print("✅ 已进入 Repayment Details 页面")
    driver.save_screenshot("repayment_details.png")

    if h5_click_bottom_button(driver, "Repay", timeout=15):
        time.sleep(2)
        driver.save_screenshot("after_repay_click.png")
        handle_browser_chooser_if_present(driver, timeout=6)
    else:
        print("⚠️ 未能点击 Repay 按钮")

    driver.save_screenshot("after_repay.png")
    print("✅ Go to repay 流程完成")
