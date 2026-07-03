#!/usr/bin/env python
"""CLI 入口：等价于原单文件脚本主流程，供 Jenkins 直接调用"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from loanadvisor.core.driver_factory import create_driver
from loanadvisor.flows.dispatcher import dispatch_post_login_flow
from loanadvisor.flows.login_flow import run_login


def main() -> int:
    driver = create_driver()
    try:
        run_login(driver)
        dispatch_post_login_flow(driver)
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
