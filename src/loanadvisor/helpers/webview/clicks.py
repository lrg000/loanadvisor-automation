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

def click_any_target_text(driver, texts, timeout=2, interval=0.5):
    """
    点击 H5 页面中任意一个目标文本（稳定版）

    支持：
    - Next
    - Go to repay
    - Apply
    """

    end_time = time.time() + timeout

    js_click = """
    const targets = arguments[0];

    function findClickable(el) {
        if (!el) return null;

        // 向上找可点击父节点
        while (el) {
            const tag = el.tagName.toLowerCase();

            const clickable =
                tag === 'button' ||
                tag === 'a' ||
                el.getAttribute('role') === 'button' ||
                el.onclick ||
                el.getAttribute('onclick');

            if (clickable) return el;

            el = el.parentElement;
        }
        return null;
    }

    const elements = document.querySelectorAll('body *');

    for (let el of elements) {
        const text = (el.innerText || '').trim();
        if (!text) continue;

        for (let t of targets) {
            if (text === t || text.includes(t)) {

                const clickable = findClickable(el);
                if (clickable) {
                    clickable.scrollIntoView({block: "center"});
                    clickable.click();
                    return t;
                }
            }
        }
    }

    return null;
    """

    while time.time() < end_time:

        # ===== 1. JS 优先点击 =====
        try:
            clicked = driver.execute_script(js_click, texts)
            if clicked:
                print(f"✅ JS点击成功: {clicked}")
                return clicked
        except Exception as e:
            print("JS执行失败:", e)

        # ===== 2. Selenium fallback =====
        for t in texts:
            try:
                el = WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located(
                        (By.XPATH, f"//*[contains(normalize-space(), '{t}')]")
                    )
                )

                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)

                try:
                    WebDriverWait(driver, 2).until(EC.element_to_be_clickable(el))
                    el.click()
                    print(f"✅ XPath点击成功: {t}")
                    return t
                except:
                    driver.execute_script("arguments[0].click();", el)
                    print(f"✅ JS fallback点击成功: {t}")
                    return t

            except:
                continue

        time.sleep(interval)

    raise TimeoutException(f"未找到可点击目标: {texts}")


def wait_for_h5_text(driver, text, timeout=20):
    """等待 H5 页面出现指定文本"""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script(
                "return document.body && document.body.innerText.includes(arguments[0])",
                text
            )
        )
        return True
    except Exception:
        return False


