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

from loanadvisor.helpers.webview.clicks import click_any_target_text, wait_for_h5_text
from loanadvisor.helpers.webview.h5 import h5_click_modal_button
from loanadvisor.helpers.webview.switcher import switch_to_real_webview

def click_home_apply_if_needed(driver, timeout=12):
    """
    KYC 完成后若回到首页：先关可选弹窗，再点击 Apply。
    若已在 Success 页或已无 Apply 按钮，则跳过（避免重复点击）。
    """
    try:
        switch_to_real_webview(driver, timeout=15)
    except Exception as e:
        print("WebView 切换跳过:", e)

    time.sleep(1.5)

    if wait_for_h5_text(driver, "Success", timeout=2):
        print("⏭️ 已在 Apply 成功页，跳过点击 Apply")
        return True

    dismiss_optional_home_loan_popup(driver)

    if not wait_for_h5_text(driver, "Apply", timeout=8):
        print("ℹ️ 首页未检测到 Apply，可能已进入申请流程")
        return True

    print("--- 点击首页 Apply 进入申请 ---")
    driver.save_screenshot("before_click_apply.png")

    try:
        click_any_target_text(driver, ["Apply"], timeout=timeout)
    except TimeoutException:
        if dismiss_optional_home_loan_popup(driver, timeout=5):
            click_any_target_text(driver, ["Apply"], timeout=timeout)
        else:
            driver.save_screenshot("click_apply_fail.png")
            raise TimeoutException("KYC 完成后未能点击首页 Apply")

    time.sleep(1.5)
    driver.save_screenshot("after_click_apply.png")
    print("✅ 已点击首页 Apply")
    return True

def _h5_optional_loan_plan_popup_visible(driver):
    """检测首页可选营销弹窗「Plan your next loan with one click」"""
    try:
        body = driver.execute_script("return document.body.innerText || ''") or ""
        return (
            "Plan your next loan" in body
            or (
                "Timely repayment" in body
                and "Start now" in body
                and "Close" in body
            )
        )
    except Exception:
        return False


def dismiss_optional_home_loan_popup(driver, timeout=4):
    """
    关闭首页可选营销弹窗（非必现）。
    弹窗标题：Plan your next loan with one click；点击 Close 关闭。
    未检测到弹窗则静默跳过。
    """
    try:
        switch_to_real_webview(driver, timeout=8)
    except Exception as e:
        print(f"WebView 切换跳过(关闭弹窗): {e}")

    if not _h5_optional_loan_plan_popup_visible(driver):
        return False

    print("--- 检测到可选贷款计划弹窗，点击 Close ---")
    driver.save_screenshot("optional_loan_popup_before_close.png")

    end_time = time.time() + timeout
    clicked = False
    while time.time() < end_time and not clicked:
        try:
            clicked = bool(
                driver.execute_script(
                    """
                    const body = document.body.innerText || '';
                    if (!body.includes('Plan your next loan') &&
                        !(body.includes('Timely repayment') && body.includes('Start now'))) {
                        return false;
                    }
                    let modal = null;
                    for (const el of document.querySelectorAll('div, section, dialog, [role=dialog]')) {
                        const t = el.innerText || '';
                        if (!t.includes('Plan your next loan')) continue;
                        const r = el.getBoundingClientRect();
                        if (r.width > 200 && r.height > 200) {
                            modal = el;
                            break;
                        }
                    }
                    const root = modal || document.body;
                    for (const el of root.querySelectorAll('button, div, span, a, [role=button]')) {
                        const t = (el.innerText || '').trim();
                        if (t !== 'Close') continue;
                        const r = el.getBoundingClientRect();
                        if (r.width < 40 || r.height < 16) continue;
                        el.scrollIntoView({block: 'center', behavior: 'instant'});
                        el.click();
                        return true;
                    }
                    return false;
                    """
                )
            )
        except Exception:
            pass

        if not clicked:
            clicked = h5_click_modal_button(driver, "Close", timeout=2)
        if not clicked:
            time.sleep(0.5)

    if clicked:
        time.sleep(1.0)
        driver.save_screenshot("optional_loan_popup_after_close.png")
        print("✅ 已关闭可选贷款计划弹窗")
        return True

    print("⚠️ 检测到贷款计划弹窗但未能点击 Close")
    return False


def click_home_target_with_optional_popup(driver, texts, timeout=8):
    """点击首页目标按钮；若被可选弹窗遮挡则先 Close 再重试"""
    dismiss_optional_home_loan_popup(driver)
    try:
        return click_any_target_text(driver, texts, timeout=timeout)
    except TimeoutException:
        if dismiss_optional_home_loan_popup(driver, timeout=5):
            return click_any_target_text(driver, texts, timeout=timeout)
        raise
