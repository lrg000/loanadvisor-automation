"""KYC 流程路由：按 WebView URL 后缀决定起始步骤"""
from __future__ import annotations

from loanadvisor.flows.kyc_aadhaar_flow import fill_kyc_aadhaar_ocr
from loanadvisor.flows.kyc_bank_flow import fill_kyc_bank_account_form
from loanadvisor.flows.kyc_liveness_flow import fill_kyc_silent_liveness
from loanadvisor.helpers.webview.h5 import fill_basic_info_form, fill_reference_contacts_form

KYC_FLOW_STEPS = (
    ("basicInfo", "Basic info", fill_basic_info_form),
    ("emergencyContacts", "Reference Contacts", fill_reference_contacts_form),
    ("identity", "KYC Aadhaar OCR", fill_kyc_aadhaar_ocr),
    ("face", "Silent Liveness", fill_kyc_silent_liveness),
    ("bank", "Bank Account", fill_kyc_bank_account_form),
)

_KYC_ROUTE_ALIASES = {
    "basicinfo": 0,
    "emergencycontacts": 1,
    "referencecontacts": 1,
    "identity": 2,
    "kycprocess": 2,
    "face": 3,
    "liveness": 3,
    "selfie": 3,
    "bank": 4,
    "bankinfo": 4,
}


def get_h5_route_suffix(driver) -> str:
    """获取当前 H5 hash 路由后缀，如 basicInfo、emergencyContacts"""
    try:
        route = driver.execute_script(
            """
            const h = (window.location.hash || '').replace(/^#\\/?/, '');
            if (h) return h.split('?')[0].split('/')[0];
            const href = window.location.href || '';
            if (href.includes('#/')) return href.split('#/').pop().split('?')[0].split('/')[0];
            return '';
            """
        )
        return (route or "").strip()
    except Exception:
        return ""


def resolve_kyc_start_index(route_suffix: str) -> int:
    """根据 URL 后缀决定从哪一步开始执行（含后续所有步骤）"""
    route = (route_suffix or "").strip()
    if not route:
        return 0

    route_low = route.lower()
    for i, (key, _name, _fn) in enumerate(KYC_FLOW_STEPS):
        if key.lower() == route_low:
            return i

    for i, (key, _name, _fn) in enumerate(KYC_FLOW_STEPS):
        key_low = key.lower()
        if key_low in route_low or route_low in key_low:
            return i

    if route_low in _KYC_ROUTE_ALIASES:
        return _KYC_ROUTE_ALIASES[route_low]

    print(f"⚠️ 未识别 KYC 路由 /{route}，从 Basic info 开始")
    return 0


def run_kyc_steps_from_route(driver, start_index: int = 0) -> None:
    """从指定步骤起依次执行 KYC 及后续步骤"""
    total = len(KYC_FLOW_STEPS)
    start_index = max(0, min(start_index, total - 1))

    if start_index > 0:
        skipped = [name for _r, name, _f in KYC_FLOW_STEPS[:start_index]]
        print(f"⏭️ 跳过已完成步骤: {', '.join(skipped)}")

    for i in range(start_index, total):
        route, name, fn = KYC_FLOW_STEPS[i]
        print(f"--- KYC [{i + 1}/{total}] {name} (/#/{route}) ---")
        fn(driver)
