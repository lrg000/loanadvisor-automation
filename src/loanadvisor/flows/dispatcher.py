"""登录后按页面状态分支执行业务流程"""
from __future__ import annotations

from loanadvisor.flows.apply_flow import run_apply_flow
from loanadvisor.flows.next_flow import run_next_flow
from loanadvisor.flows.repay_flow import run_go_to_repay_flow
from loanadvisor.helpers.webview.home_actions import click_home_target_with_optional_popup
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
    )
    print("检测到页面状态:", target)
    print("contexts:", driver.contexts)
    print("current_context:", driver.current_context)

    if target == "Next":
        run_next_flow(driver)
    elif target == "Go to repay":
        run_go_to_repay_flow(driver)
    elif target == "Apply":
        run_apply_flow(driver)
    else:
        print(f"⚠️ 未知状态: {target}，跳过后续流程")

    return target or "unknown"
