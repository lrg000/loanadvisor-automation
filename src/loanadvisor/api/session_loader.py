"""
接口测试会话加载（预留扩展）

login_result.json 结构示例：
- final_url: H5 入口 URL
- localStorage.BaseInfo: 含 customerId、token、phone 等
- token: 从 localStorage 提取的 token 字段

后续接口测试可从此模块加载会话，无需重复 UI 登录。
"""
from __future__ import annotations

import json
from typing import Any

from loanadvisor.core.config import settings
from loanadvisor.core.login_session import load_login_result


def get_base_info(login_data: dict | None = None) -> dict:
    data = login_data or load_login_result()
    raw = (data.get("localStorage") or {}).get("BaseInfo") or "{}"
    return json.loads(raw)


def get_api_token(login_data: dict | None = None) -> str | None:
    base = get_base_info(login_data)
    return base.get("token")


def get_customer_id(login_data: dict | None = None) -> int | None:
    base = get_base_info(login_data)
    cid = base.get("customerId")
    return int(cid) if cid is not None else None


def get_api_base_url(login_data: dict | None = None) -> str:
    base = get_base_info(login_data)
    return (base.get("baseUrl") or "http://192.168.31.217:7066/").rstrip("/")


class ApiSession:
    """轻量 API 客户端占位，后续可扩展 requests 封装"""

    def __init__(self, login_data: dict | None = None):
        self.login_data = login_data or load_login_result()
        self.base_url = get_api_base_url(self.login_data)
        self.token = get_api_token(self.login_data)
        self.customer_id = get_customer_id(self.login_data)

    def default_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-Requested-With": settings.app_package,
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
        }
        if self.token:
            headers["token"] = self.token
        return headers

    def summary(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "customer_id": self.customer_id,
            "has_token": bool(self.token),
            "login_result": str(settings.login_result_path),
        }
