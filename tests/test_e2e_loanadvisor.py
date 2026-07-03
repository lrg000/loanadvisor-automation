"""E2E：登录 → 分支流程（Next / Repay / Apply）"""
import pytest

from loanadvisor.flows.dispatcher import dispatch_post_login_flow


@pytest.mark.e2e
def test_post_login_business_flow(logged_in_driver):
    target = dispatch_post_login_flow(logged_in_driver)
    assert target in ("Next", "Go to repay", "Apply"), f"未知或未识别页面状态: {target}"
