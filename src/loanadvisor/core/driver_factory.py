"""Appium Driver 工厂"""
from __future__ import annotations

from appium import webdriver
from appium.options.android import UiAutomator2Options

from loanadvisor.core.config import settings


def create_driver():
    options = UiAutomator2Options().load_capabilities(settings.capabilities)
    driver = webdriver.Remote(settings.appium_server, options=options)
    driver.implicitly_wait(0)
    print("App启动成功")
    return driver
