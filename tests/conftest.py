"""pytest  fixtures"""
from __future__ import annotations

import pytest

from loanadvisor.core.config import settings
from loanadvisor.core.driver_factory import create_driver
from loanadvisor.flows.dispatcher import dispatch_post_login_flow
from loanadvisor.flows.login_flow import run_login


@pytest.fixture(scope="session")
def appium_driver():
    driver = create_driver()
    yield driver
    driver.quit()


@pytest.fixture(scope="session")
def logged_in_driver(appium_driver):
    run_login(appium_driver)
    yield appium_driver


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end Appium tests")
    config.addinivalue_line("markers", "api: API tests using login_result.json")
