# Loan Advisor 自动化测试框架

基于 `appium自动化测试_备份.py` 重构的 **企业级 Jenkins E2E 工程**，与备份脚本 **业务完全对齐**：

- 原生登录（OTP）
- **完整 KYC 链路**：Basic info → Reference Contacts → Aadhaar OCR → 静默活体 → 绑卡
- **智能续跑**：按 WebView URL 后缀（`#/basicInfo`、`#/identity` 等）自动跳过已完成步骤
- 分支流程：Next / Go to repay / Apply
- MySQL 字段非空验证 + Allure 报告
- **login_result.json** 会话落盘（供接口测试扩展）

## 目录结构

```
loanadvisor_automation/
├── Jenkinsfile                 # CI Pipeline（支持设备/账号参数注入）
├── run.py                      # CLI 入口
├── config/env.example          # 环境变量模板 → 复制为 .env
├── scripts/
│   ├── split_from_backup.py    # 从备份脚本同步业务逻辑
│   └── jenkins_preflight.ps1   # adb / Appium 预检
├── src/loanadvisor/
│   ├── core/                   # config、driver、login_session
│   ├── flows/
│   │   ├── login_flow.py
│   │   ├── dispatcher.py       # Next / Go to repay / Apply 分支
│   │   ├── next_flow.py        # Begin Verification → KYC → Apply → DB
│   │   ├── kyc_router.py       # ★ URL 路由续跑编排
│   │   ├── kyc_aadhaar_flow.py
│   │   ├── kyc_liveness_flow.py
│   │   ├── kyc_bank_flow.py
│   │   ├── repay_flow.py
│   │   └── apply_flow.py
│   └── helpers/
│       ├── native/             # 权限、smart_click、相机
│       ├── webview/            # H5 表单、WebView 切换
│       ├── kyc/                # ★ OCR 确认弹窗、原生拍照
│       └── db/                 # MySQL 验证、Allure
└── tests/                      # pytest e2e / api
```

## KYC 流程（与备份脚本一致）

| 顺序 | H5 路由 | 函数 |
|------|---------|------|
| 1 | `#/basicInfo` | `fill_basic_info_form` |
| 2 | `#/emergencyContacts` | `fill_reference_contacts_form` |
| 3 | `#/identity` | `fill_kyc_aadhaar_ocr` |
| 4 | `#/face` | `fill_kyc_silent_liveness` |
| 5 | `#/bank` | `fill_kyc_bank_account_form` |

`run_next_flow` 在 **Begin Verification** 后读取当前 URL 后缀，从对应步骤续跑至绑卡，再执行 `run_apply_flow` 与 DB 验证。

## 快速开始

```powershell
cd loanadvisor_automation
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -e .

copy config\env.example .env
# 编辑 .env：DEVICE_NAME、LOGIN_PHONE、DB_PASSWORD 等

$env:PYTHONPATH="src"
python run.py
```

**无需改代码**：所有设备/账号/KYC 测试数据通过 `.env` 或环境变量配置。

## 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `DEVICE_NAME` | adb 设备 ID | `4HRSJF8P9HZ9DQMJ` |
| `PLATFORM_VERSION` | Android 版本 | `12` |
| `APP_PACKAGE` | 应用包名 | `com.rajwiseguide.loanadvisor.app` |
| `LOGIN_PHONE` | 登录手机号 | `9110001254` |
| `LOGIN_OTP` | OTP | `123456` |
| `KYC_OCR_DOB` / `KYC_OCR_PAN` | OCR 确认页 | 见 env.example |
| `KYC_BANK_IFSC` / `KYC_BANK_ACCOUNT` | 绑卡 | 见 env.example |
| `DB_*` | MySQL 验证 | 见 env.example |

## Jenkins

完整 **GitHub 上传 + Jenkins 集成** 逐步清单（可直接复制命令）：[`docs/GITHUB_JENKINS_CHECKLIST.md`](docs/GITHUB_JENKINS_CHECKLIST.md)

1. 安装 Appium、adb、Python 3.10+
2. 在 Jenkins 凭据或节点上准备 `.env`（或由 Pipeline 从 `env.example` 复制后手动改）
3. 创建 Pipeline 任务，Script Path = `loanadvisor_automation/Jenkinsfile`
4. 构建参数可覆盖：`DEVICE_NAME_OVERRIDE`、`LOGIN_PHONE_OVERRIDE`、`PLATFORM_VERSION_OVERRIDE`、`APP_PACKAGE_OVERRIDE`

默认执行 `python run.py`（完整 E2E + DB 验证）。勾选 `RUN_PYTEST` 可额外跑 pytest。

## 从备份脚本同步业务逻辑

备份脚本更新后，在项目根执行：

```powershell
python scripts/split_from_backup.py
```

会重新生成 `helpers/` 与 `flows/` 下各模块（**保留** 手写的 `kyc_router.py`）。同步后请检查：

- `helpers/kyc/shared.py` 中 `KYC_*_TEST_DATA` 是否仍指向 `settings`
- `flows/next_flow.py` 是否使用 `get_h5_route_suffix` / `resolve_kyc_start_index`

## Pytest

```powershell
pytest tests -m e2e -v
pytest tests -m api -v
```

## 产出物

- `artifacts/login_result.json` — 登录会话
- `reports/allure-results/` — DB 验证 Allure 原始数据
- `kyc_*.png`、`after_*.png` — 流程截图（Jenkins 归档）

详细业务流程见上级目录：`appium自动化测试_业务说明.md`
