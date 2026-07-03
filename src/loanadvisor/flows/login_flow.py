"""原生登录流程"""
from __future__ import annotations

from appium.webdriver.common.appiumby import AppiumBy

from loanadvisor.core.config import settings
from loanadvisor.core.login_session import capture_webview_login
from loanadvisor.helpers.native.interactions import hide_keyboard_native, smart_click, smart_input
from loanadvisor.helpers.webview.switcher import switch_to_real_webview


def run_login(driver) -> None:
    """Agree → 手机号 OTP 登录 → 切换 WebView → 保存 login_result.json"""
    smart_click(
        driver,
        AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().text("Agree & Continue")',
        timeout=10,
    )
    smart_click(
        driver,
        AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().className("android.view.View").instance(12)',
        timeout=10,
    )
    smart_click(
        driver,
        AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().text("Login with Mobile Number")',
        timeout=10,
    )
    hide_keyboard_native(driver)
    smart_input(
        driver,
        AppiumBy.CLASS_NAME,
        "android.widget.EditText",
        settings.login_phone,
        timeout=10,
    )
    hide_keyboard_native(driver)
    smart_click(
        driver,
        AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().text("Send OTP")',
        timeout=10,
    )
    smart_input(
        driver,
        AppiumBy.CLASS_NAME,
        "android.widget.EditText",
        settings.login_otp,
        timeout=10,
    )
    smart_click(
        driver,
        AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().text("Verify & Login")',
        timeout=10,
    )
    print("登录流程完成")

    switch_to_real_webview(driver)
    capture_webview_login(driver)
