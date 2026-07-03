#!/usr/bin/env python
"""从 appium自动化测试_备份.py 拆分为框架模块（与备份脚本业务对齐）"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "loanadvisor"
BACKUP = Path(__file__).resolve().parents[2] / "appium自动化测试_备份.py"

COMMON_HEADER = '''"""业务逻辑源自 appium自动化测试_备份.py"""
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
'''

H5_IMPORTS = """
from loanadvisor.helpers.native.interactions import swipe_up
from loanadvisor.helpers.native.permissions import handle_permission_popup
from loanadvisor.helpers.webview.clicks import click_any_target_text, wait_for_h5_text
from loanadvisor.helpers.webview.switcher import switch_to_real_webview

swipe_up_h5 = swipe_up
"""

KYC_SHARED_IMPORTS = """
from loanadvisor.helpers.native.permissions import handle_permission_popup
from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import h5_click_bottom_button, h5_click_modal_button
from loanadvisor.helpers.webview.switcher import switch_to_real_webview
"""

KYC_CONFIRM_IMPORTS = """
from loanadvisor.helpers.kyc.shared import (
    KYC_OCR_TEST_DATA,
    ensure_kyc_webview,
    generate_valid_pan,
    is_valid_pan,
    normalize_pan_value,
)
from loanadvisor.helpers.native.permissions import handle_permission_popup
from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import (
    h5_click_text_and_parents,
    h5_fill_text_field,
    h5_hide_keyboard,
    h5_tap_at,
    h5_vue_click_element,
    h5_w3c_tap_element,
)
from loanadvisor.helpers.webview.switcher import switch_to_real_webview
"""

KYC_AADHAAR_IMPORTS = """
from loanadvisor.helpers.kyc.confirm_modal import (
    _h5_click_date_picker_confirm,
    _h5_is_date_picker_open,
    h5_fill_kyc_confirm_form,
    h5_kyc_confirm_form_likely_ready,
)
from loanadvisor.helpers.kyc.shared import (
    KYC_OCR_TEST_DATA,
    _h5_aadhaar_ocr_preview_ready,
    _kyc_navigate_to_aadhaar_upload,
    _kyc_trigger_camera_allow,
    _native_complete_photo_selection,
    _wait_for_aadhaar_photo_ready,
    ensure_kyc_webview,
    generate_valid_pan,
    h5_wait_and_click_submit,
    is_valid_pan,
)
from loanadvisor.helpers.native.permissions import handle_permission_popup
from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import h5_click_bottom_button, h5_click_form_next, h5_click_modal_button
from loanadvisor.helpers.webview.switcher import switch_to_real_webview
"""

KYC_LIVENESS_IMPORTS = """
from loanadvisor.helpers.kyc.shared import _native_take_camera_photo, ensure_kyc_webview, h5_wait_and_click_submit
from loanadvisor.helpers.native.permissions import handle_permission_popup
from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import h5_click_bottom_button, h5_click_form_next
from loanadvisor.helpers.webview.switcher import switch_to_real_webview
"""

KYC_BANK_IMPORTS = """
from loanadvisor.helpers.kyc.shared import KYC_BANK_TEST_DATA
from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import h5_click_bottom_button, h5_click_form_next, h5_hide_keyboard, swipe_up_h5
from loanadvisor.helpers.webview.switcher import switch_to_real_webview
"""

NEXT_FLOW_IMPORTS = """
from loanadvisor.flows.apply_flow import run_apply_flow
from loanadvisor.flows.kyc_router import get_h5_route_suffix, resolve_kyc_start_index, run_kyc_steps_from_route
from loanadvisor.helpers.db.verify import generate_allure_db_report, verify_apply_db_fields
from loanadvisor.helpers.native.permissions import handle_all_permission_popups
from loanadvisor.helpers.webview.clicks import click_any_target_text
from loanadvisor.helpers.webview.settings import handle_app_usage_settings
from loanadvisor.helpers.webview.switcher import switch_to_real_webview
"""

HOME_ACTIONS_IMPORTS = """
from loanadvisor.helpers.webview.clicks import click_any_target_text, wait_for_h5_text
from loanadvisor.helpers.webview.h5 import h5_click_modal_button
from loanadvisor.helpers.webview.switcher import switch_to_real_webview
"""

APPLY_FLOW_IMPORTS = """
from loanadvisor.helpers.native.permissions import handle_all_permission_popups
from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import h5_click_success_confirm
from loanadvisor.helpers.webview.home_actions import click_home_apply_if_needed
from loanadvisor.helpers.webview.settings import handle_app_usage_settings
from loanadvisor.helpers.webview.switcher import switch_to_real_webview
"""

REPAY_FLOW_IMPORTS = """
from loanadvisor.helpers.webview.clicks import wait_for_h5_text
from loanadvisor.helpers.webview.h5 import (
    h5_click_bottom_button,
    h5_click_repay_loan_button,
    h5_repay_details_visible,
)
from loanadvisor.helpers.webview.home_actions import dismiss_optional_home_loan_popup
from loanadvisor.helpers.webview.settings import handle_browser_chooser_if_present
from loanadvisor.helpers.webview.switcher import switch_to_real_webview
"""

VERIFY_HEADER = COMMON_HEADER + """
from loanadvisor.core.config import settings

APPLY_DB_CONFIG = settings.db_config
APPLY_DB_TABLE_FIELDS = settings.db_table_fields
ALLURE_RESULTS_DIR = str(settings.allure_results_dir)
ALLURE_REPORT_DIR = str(settings.allure_report_dir)
_SCRIPT_DIR = str(settings.allure_results_dir.parent.parent)
"""

SECTIONS = [
    ("helpers/native/permissions.py", 184, 401, COMMON_HEADER),
    (
        "helpers/native/interactions.py",
        402,
        697,
        COMMON_HEADER + "\nfrom loanadvisor.helpers.native.permissions import handle_permission_popup\n",
    ),
    ("helpers/webview/switcher.py", 699, 748, COMMON_HEADER),
    ("helpers/webview/clicks.py", 847, 958, COMMON_HEADER),
    (
        "helpers/webview/settings.py",
        959,
        1187,
        COMMON_HEADER + "\nfrom loanadvisor.helpers.native.interactions import swipe_up\n",
    ),
    ("helpers/webview/h5.py", 1189, 3819, COMMON_HEADER + H5_IMPORTS),
    ("helpers/kyc/shared.py", 3822, 4225, COMMON_HEADER + KYC_SHARED_IMPORTS),
    ("helpers/kyc/confirm_modal.py", 4227, 5243, COMMON_HEADER + KYC_CONFIRM_IMPORTS),
    ("flows/kyc_aadhaar_flow.py", 5245, 5344, COMMON_HEADER + KYC_AADHAAR_IMPORTS),
    ("flows/kyc_liveness_flow.py", 5347, 5501, COMMON_HEADER + KYC_LIVENESS_IMPORTS),
    ("flows/kyc_bank_flow.py", 5503, 5825, COMMON_HEADER + KYC_BANK_IMPORTS),
    ("flows/next_flow.py", 5947, 5985, COMMON_HEADER + NEXT_FLOW_IMPORTS),
    ("flows/repay_flow.py", 5988, 6062, COMMON_HEADER + REPAY_FLOW_IMPORTS),
    ("helpers/db/verify.py", 6095, 6377, VERIFY_HEADER),
    ("flows/apply_flow.py", 6380, 6409, COMMON_HEADER + APPLY_FLOW_IMPORTS),
]


def main():
    lines = BACKUP.read_text(encoding="utf-8").splitlines()
    for rel, start, end, header in SECTIONS:
        body = "\n".join(lines[start - 1 : end]) + "\n"
        path = SRC / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(header + "\n" + body, encoding="utf-8")
        print("wrote", rel)

    _write_home_actions(lines)

    kyc_pkg = SRC / "helpers" / "kyc" / "__init__.py"
    kyc_pkg.write_text('"""KYC 身份验证相关 helpers"""\n', encoding="utf-8")
    print("wrote helpers/kyc/__init__.py")

    _patch_shared_test_data(SRC / "helpers" / "kyc" / "shared.py")
    _patch_next_flow_router(SRC / "flows" / "next_flow.py")
    _patch_apply_flow(SRC / "flows" / "apply_flow.py")
    _patch_dispatcher(SRC / "flows" / "dispatcher.py")
    _patch_kyc_aadhaar_manual_wait(SRC / "flows" / "kyc_aadhaar_flow.py")


def _write_home_actions(lines: list[str]) -> None:
    """首页可选弹窗 + Apply 点击（备份脚本中两处定义合并）"""
    header = COMMON_HEADER + HOME_ACTIONS_IMPORTS
    part1 = "\n".join(lines[5906:5944]) + "\n\n"
    part2 = "\n".join(lines[6411:6507]) + "\n"
    content = header + "\n" + part1 + part2
    content = content.replace(
        "def _click_home_apply_if_needed", "def click_home_apply_if_needed"
    )
    content = content.replace(
        "def _click_home_target_with_optional_popup",
        "def click_home_target_with_optional_popup",
    )
    path = SRC / "helpers" / "webview" / "home_actions.py"
    path.write_text(content, encoding="utf-8")
    print("wrote helpers/webview/home_actions.py")


def _patch_shared_test_data(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = '''KYC_OCR_TEST_DATA = {
    "full_name": "Mohammed Saif Farooqi",
    "date_of_birth": "31/07/2000",
    "pan_number": "ABCDE1234F",
}

KYC_BANK_TEST_DATA = {
    "ifsc": "SBIN0010913",
    "account_no": "1234567890",
    "account_confirm": "1234567890",
}'''
    new = '''KYC_OCR_TEST_DATA = {
    "full_name": settings.kyc_ocr_full_name,
    "date_of_birth": settings.kyc_ocr_dob,
    "pan_number": settings.kyc_ocr_pan,
}

KYC_BANK_TEST_DATA = {
    "ifsc": settings.kyc_bank_ifsc,
    "account_no": settings.kyc_bank_account,
    "account_confirm": settings.kyc_bank_account,
}'''
    if old in text:
        path.write_text(text.replace(old, new), encoding="utf-8")
        print("patched helpers/kyc/shared.py test data → settings")


def _patch_next_flow_router(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace("_get_h5_route_suffix", "get_h5_route_suffix")
    text = text.replace("_resolve_kyc_start_index", "resolve_kyc_start_index")
    path.write_text(text, encoding="utf-8")
    print("patched flows/next_flow.py router imports")


def _patch_apply_flow(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace("_click_home_apply_if_needed", "click_home_apply_if_needed")
    path.write_text(text, encoding="utf-8")
    print("patched flows/apply_flow.py → click_home_apply_if_needed")


def _patch_dispatcher(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = '''from loanadvisor.helpers.webview.clicks import click_any_target_text


def dispatch_post_login_flow(driver) -> str:
    target = click_any_target_text(
        driver,
        ["Next", "Go to repay", "Apply"],
        timeout=5,
    )'''
    new = '''from loanadvisor.helpers.webview.home_actions import click_home_target_with_optional_popup
from loanadvisor.helpers.webview.switcher import switch_to_real_webview


def dispatch_post_login_flow(driver) -> str:
    try:
        switch_to_real_webview(driver, timeout=15)
    except Exception as e:
        print("WebView 切换跳过:", e)

    target = click_home_target_with_optional_popup(
        driver,
        ["Next", "Go to repay", "Apply"],
        timeout=8,
    )'''
    if old in text:
        path.write_text(text.replace(old, new), encoding="utf-8")
        print("patched flows/dispatcher.py → home popup + target click")
    else:
        print("warn: dispatcher.py patch skipped (content changed)")


def _patch_kyc_aadhaar_manual_wait(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = 'manual_wait_sec = int(os.environ.get("KYC_PHOTO_MANUAL_WAIT_SEC", "300"))'
    new = "manual_wait_sec = settings.kyc_photo_manual_wait_sec"
    if old in text:
        path.write_text(text.replace(old, new), encoding="utf-8")
        print("patched flows/kyc_aadhaar_flow.py → settings.kyc_photo_manual_wait_sec")


if __name__ == "__main__":
    main()
