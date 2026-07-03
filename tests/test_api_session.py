"""API 测试占位：基于 login_result.json（需先跑 E2E 或手动放置 artifacts）"""
import pytest

from loanadvisor.api.session_loader import ApiSession
from loanadvisor.core.config import settings


@pytest.mark.api
def test_login_result_session_loadable():
    if not settings.login_result_path.is_file():
        pytest.skip("无 login_result.json，请先执行 E2E 登录流程")
    session = ApiSession()
    summary = session.summary()
    assert summary["has_token"], "login_result 中应包含 token"
    assert summary["customer_id"], "login_result 中应包含 customerId"
