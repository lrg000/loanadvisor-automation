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

from loanadvisor.flows.apply_flow import run_apply_flow
from loanadvisor.flows.kyc_router import get_h5_route_suffix, resolve_kyc_start_index, run_kyc_steps_from_route
from loanadvisor.helpers.db.verify import generate_allure_db_report, verify_apply_db_fields
from loanadvisor.helpers.native.permissions import handle_all_permission_popups
from loanadvisor.helpers.webview.clicks import click_any_target_text
from loanadvisor.helpers.webview.settings import handle_app_usage_settings
from loanadvisor.helpers.webview.switcher import switch_to_real_webview

def run_next_flow(driver):
    """
    Next 状态：用户处于引导/验证前置步骤
    权限弹窗 → Usage Access → Begin Verification → Basic info → MySQL DB 验证
    """
    print("=== 执行 Next 流程 ===")

    handle_all_permission_popups(driver)
    print("当前 context:", driver.current_context)
    driver.save_screenshot("after_next.png")

    handle_app_usage_settings(driver)

    click_any_target_text(
        driver,
        ["Begin Verification"],
        timeout=5
    )

    route_suffix = ""
    try:
        switch_to_real_webview(driver, timeout=15)
        route_suffix = get_h5_route_suffix(driver)
        if route_suffix:
            print(f"✅ Begin Verification 后进入: /{route_suffix}")
    except Exception as e:
        print("WebView 切换跳过:", e)

    start_idx = resolve_kyc_start_index(route_suffix)
    run_kyc_steps_from_route(driver, start_idx)

    run_apply_flow(driver)
    

    time.sleep(5)
    db_result = verify_apply_db_fields()
    generate_allure_db_report(db_result)
    assert db_result["passed"], "Kyc DB 验证失败:\n" + "\n".join(db_result["errors"])

    print("✅ Next 流程完成")
