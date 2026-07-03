"""登录会话：内存态 + login_result.json 持久化（供后续接口测试复用）"""
from __future__ import annotations

import json
from typing import Any

from loanadvisor.core.config import settings

LOGIN_DATA: dict[str, Any] = {}


def extract_token(storage: dict) -> dict | None:
    keys = ["token", "accessToken", "jwt", "Authorization", "session", "auth"]
    for k, v in storage.items():
        if any(x.lower() in k.lower() for x in keys):
            return {k: v}
    return None


def save_login_result(data: dict | None = None) -> str:
    payload = LOGIN_DATA if data is None else data
    path = settings.login_result_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"登录数据已保存：{path}")
    return str(path)


def load_login_result() -> dict:
    path = settings.login_result_path
    if not path.is_file():
        raise FileNotFoundError(f"未找到 login_result.json: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def capture_webview_login(driver) -> dict:
    """登录后采集 H5 localStorage，写入 LOGIN_DATA 并落盘"""
    current_url = driver.execute_script("return window.location.href")
    print("当前H5 URL:", current_url)
    LOGIN_DATA["final_url"] = current_url

    storage = driver.execute_script(
        """
        var data = {};
        for (var i = 0; i < localStorage.length; i++) {
            var key = localStorage.key(i);
            data[key] = localStorage.getItem(key);
        }
        return data;
        """
    )
    print("localStorage:", storage)
    LOGIN_DATA["localStorage"] = storage

    token = extract_token(storage)
    LOGIN_DATA["token"] = token
    print("提取token:", token)

    save_login_result()
    return LOGIN_DATA
