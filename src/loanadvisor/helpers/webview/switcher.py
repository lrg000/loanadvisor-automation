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

def switch_to_real_webview(driver, timeout=30, keyword=None, min_text_len=20):
    """
    切换到真正渲染了业务内容的 WebView。
    keyword: 如果知道目标页面 URL 里的特征字符串（比如域名片段），传进来做精确匹配。
             不传则用"页面文字长度"判断是否是有内容的真实页面。
    """
    WebDriverWait(driver, timeout).until(lambda d: len(d.contexts) > 1)

    end_time = time.time() + timeout
    last_seen = {}

    while time.time() < end_time:
        contexts = driver.contexts
        for c in contexts:
            if "WEBVIEW" not in c:
                continue
            try:
                driver.switch_to.context(c)

                url = driver.execute_script("return window.location.href")
                ready = driver.execute_script("return document.readyState")
                text_len = driver.execute_script(
                    "return document.body ? document.body.innerText.length : 0"
                )
                last_seen[c] = {"url": url, "ready": ready, "text_len": text_len}

                if ready != "complete":
                    continue

                if keyword:
                    if keyword in (url or ""):
                        print(f"切换成功(关键词匹配): {c}, url={url}")
                        return c
                else:
                    if text_len >= min_text_len:
                        print(f"切换成功(有内容): {c}, url={url}, text_len={text_len}")
                        return c

            except Exception as e:
                last_seen[c] = {"error": str(e)}

        # 都没匹配上，退回 native 上下文，等一会再重新枚举
        try:
            driver.switch_to.context("NATIVE_APP")
        except Exception:
            pass
        time.sleep(2)

    print("调试信息 - 各context最后一次观测情况:", last_seen)
    raise Exception("WEBVIEW切换失败：超时未找到加载完成且有内容的WebView")
