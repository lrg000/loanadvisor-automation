"""运行时配置：支持 .env 文件与环境变量，便于本地开发与 Jenkins 注入"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_env_files() -> None:
    """加载项目根目录 .env（README: copy config\\env.example .env）"""
    for env_path in (PROJECT_ROOT / ".env", PROJECT_ROOT / "config" / ".env"):
        if env_path.is_file():
            load_dotenv(env_path, override=False)


_load_env_files()
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
REPORTS_DIR = PROJECT_ROOT / "reports"
SCREENSHOTS_DIR = REPORTS_DIR / "screenshots"
ALLURE_RESULTS_DIR = REPORTS_DIR / "allure-results"
ALLURE_REPORT_DIR = REPORTS_DIR / "allure-report"
LOGIN_RESULT_PATH = ARTIFACTS_DIR / "login_result.json"

for _d in (ARTIFACTS_DIR, SCREENSHOTS_DIR, ALLURE_RESULTS_DIR, ALLURE_REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)


class Settings:
    appium_server = os.getenv("APPIUM_SERVER", "http://127.0.0.1:4723")
    device_name = os.getenv("DEVICE_NAME", "4HRSJF8P9HZ9DQMJ")
    platform_version = os.getenv("PLATFORM_VERSION", "12")
    app_package = os.getenv("APP_PACKAGE", "com.rajwiseguide.loanadvisor.app")
    app_activity = os.getenv("APP_ACTIVITY", ".MainActivity")
    chromedriver_path = os.getenv(
        "CHROMEDRIVER_PATH",
        r"G:\chromedriver\chromedriver-win64\chromedriver.exe",
    )

    login_phone = os.getenv("LOGIN_PHONE", "9110001254")
    login_otp = os.getenv("LOGIN_OTP", "123456")

    kyc_ocr_full_name = os.getenv("KYC_OCR_FULL_NAME", "Mohammed Saif Farooqi")
    kyc_ocr_dob = os.getenv("KYC_OCR_DOB", "31/07/2000")
    kyc_ocr_pan = os.getenv("KYC_OCR_PAN", "ABCDE1234F")
    kyc_bank_ifsc = os.getenv("KYC_BANK_IFSC", "SBIN0010913")
    kyc_bank_account = os.getenv("KYC_BANK_ACCOUNT", "1234567890")
    kyc_photo_manual_wait_sec = int(os.getenv("KYC_PHOTO_MANUAL_WAIT_SEC", "300"))

    db_config = {
        "host": os.getenv("DB_HOST", "rm-bp18jbr0c2dj6cc34oo.rwlb.rds.aliyuncs.com"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", "C@qee7gMmKes"),
        "database": os.getenv("DB_NAME", "tea"),
        "charset": "utf8mb4",
    }

    db_table_fields = {
        "customer": ["market_id", "customer_mobile", "gad_id"],
        "customer_ext": ["andriod_id", "fcm_app_instance_id", "fcm_app_token"],
        "customer_ext_part2": ["ad_id", "quite_photo_url", "quite_photo_check_liveness"],
        "customer_device_info": [
            "base_info_address_url",
            "app_address_url",
            "call_address_url",
            "app_use_address_url",
            "gps_address_url",
        ],
    }

    @property
    def capabilities(self) -> dict:
        caps = {
            "platformName": "Android",
            "appium:automationName": "UiAutomator2",
            "appium:deviceName": self.device_name,
            "appium:platformVersion": self.platform_version,
            "appium:appPackage": self.app_package,
            "appium:appActivity": self.app_activity,
            "appium:noReset": True,
            "appium:ignoreHiddenApiPolicyError": True,
            "appium:chromedriverAutodownload": True,
        }
        if self.chromedriver_path:
            caps["appium:chromedriverExecutable"] = self.chromedriver_path
        return caps

    @property
    def allure_results_dir(self) -> Path:
        return ALLURE_RESULTS_DIR

    @property
    def allure_report_dir(self) -> Path:
        return ALLURE_REPORT_DIR

    @property
    def login_result_path(self) -> Path:
        return LOGIN_RESULT_PATH

    @property
    def screenshots_dir(self) -> Path:
        return SCREENSHOTS_DIR


settings = Settings()
