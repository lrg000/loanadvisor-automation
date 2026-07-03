"""登录后按页面状态分支执行业务流程"""
from __future__ import annotations

from loanadvisor.flows.apply_flow import run_apply_flow
from loanadvisor.flows.next_flow import run_next_flow
from loanadvisor.flows.repay_flow import run_go_to_repay_flow
from loanadvisor.helpers.webview.clicks import click_any_target_text


def dispatch_post_login_flow(driver) -> str:
    target = click_any_target_text(
        driver,
        ["Next", "Go to repay", "Apply"],
        timeout=5,
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
