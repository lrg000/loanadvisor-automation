# GitHub + Jenkins 操作清单（可直接复制执行）

> 项目：`loanadvisor_automation`  
> 适用：Windows 测试机 + Jenkins Pipeline + GitHub 独立仓库

---

## 阶段 0：上传前自检

```powershell
cd C:\Users\Win\PycharmProjects\pythonProject\loanadvisor_automation

# 确认 .env 不会被提交
if (Test-Path .env) { git check-ignore -v .env }

# 本地能跑通（Appium 需另开终端先启动）
venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
$env:PYTHONPATH="src"
python run.py
```

**检查项：**

- [ ] `.env` 不在 Git 追踪列表中
- [ ] `venv/`、`reports/`、`artifacts/` 已被忽略
- [ ] `requirements.txt` 仅含 E2E 相关包（非整机 pip freeze）
- [ ] 本地 `python run.py` 能跑通

---

## 阶段 1：GitHub 创建仓库并推送

### 1.1 GitHub 网页操作

1. 打开 https://github.com/new
2. Repository name：`loanadvisor-automation`（或自定义）
3. Visibility：Private（企业推荐）或 Public
4. **不要**勾选 “Add a README file”
5. 创建后复制仓库 URL，例如：
   ```
   https://github.com/YOUR_ORG/loanadvisor-automation.git
   ```

### 1.2 本地初始化并推送

```powershell
cd C:\Users\Win\PycharmProjects\pythonProject\loanadvisor_automation

git init
git add .
git status
# 再次确认：列表中不应出现 .env、venv/、reports/

git commit -m "Initial commit: Loan Advisor Appium E2E automation framework"

git branch -M main
git remote add origin https://github.com/YOUR_ORG/loanadvisor-automation.git
git push -u origin main
```

**私有仓库认证（二选一）：**

```powershell
# 方式 A：HTTPS + Personal Access Token（GitHub → Settings → Developer settings → PAT）
git remote set-url origin https://YOUR_TOKEN@github.com/YOUR_ORG/loanadvisor-automation.git

# 方式 B：SSH
git remote set-url origin git@github.com:YOUR_ORG/loanadvisor-automation.git
```

**检查项：**

- [ ] GitHub 上能看到 `Jenkinsfile`、`src/`、`requirements.txt`
- [ ] GitHub 上**没有** `.env` 文件

---

## 阶段 2：测试机环境安装（一次性）

在 **将要跑 Jenkins 构建的 Windows 机器** 上执行。

### 2.1 安装基础软件

| 软件 | 版本 | 验证命令 |
|------|------|----------|
| Python | 3.10+ | `python --version` |
| Java JDK | 17+ | `java -version` |
| Jenkins LTS | 最新 | 浏览器 `http://localhost:8080` |
| Node.js | 18+ | `node -v` |
| Appium 2.x | 最新 | `appium --version` |
| Android Platform Tools | 最新 | `adb devices` |
| Allure CLI | 可选 | `allure --version` |

```powershell
# Appium 2 + UiAutomator2 驱动
npm install -g appium
appium driver install uiautomator2

# Allure（可选，用于 HTML 报告）
# 下载：https://github.com/allure-framework/allure2/releases
# 解压后将 bin 目录加入 PATH
```

### 2.2 Jenkins 服务账户（重要）

Jenkins 默认以 Local System 运行，**看不到 USB 手机**。

1. `Win + R` → `services.msc`
2. 找到 **Jenkins** → 右键 **属性**
3. **登录** → 选「此账户」→ 填你的 Windows 用户名和密码
4. 重启 Jenkins 服务

验证（用**同一 Windows 用户**登录后）：

```powershell
adb devices
# 应显示 device 状态，而非 empty / unauthorized
```

**检查项：**

- [ ] Python / Java / adb / Appium 均可执行
- [ ] Jenkins 以登录用户运行
- [ ] `adb devices` 能看到测试手机

---

## 阶段 3：Jenkins 创建 Pipeline 任务

### 3.1 添加 Git 凭据（私有仓库必填）

1. Jenkins → **Manage Jenkins** → **Credentials**
2. **System** → **Global credentials** → **Add Credentials**
3. 类型：
   - **Username with password**（GitHub PAT 作密码），或
   - **SSH Username with private key**
4. ID 记下，例如：`github-loanadvisor-automation`

### 3.2 新建 Pipeline 任务

1. Jenkins 首页 → **新建任务**
2. 名称：`loanadvisor-e2e`
3. 类型：**Pipeline** → 确定

**General（可选）：**

- [ ] **Restrict where this project can be run** → Label：`appium-android`

**Pipeline 配置：**

| 字段 | 值 |
|------|-----|
| Definition | Pipeline script from SCM |
| SCM | Git |
| Repository URL | `https://github.com/YOUR_ORG/loanadvisor-automation.git` |
| Credentials | 选择上一步创建的凭据 |
| Branch | `*/main` |
| Script Path | `Jenkinsfile` |

4. 保存

**检查项：**

- [ ] Script Path = `Jenkinsfile`（独立仓库根目录）
- [ ] Git 凭据已配置（私有仓库）

---

## 阶段 4：测试机准备 `.env`（不入 Git）

Jenkins checkout 后工作区**没有** `.env`，需首次构建前或 Setup 阶段后配置。

### 方式 A：首次构建后手动编辑（新手推荐）

1. 先触发一次构建（会在 Setup 阶段从 `config/env.example` 复制 `.env`）
2. 到 Jenkins 工作区目录编辑 `.env`，例如：
   ```
   C:\ProgramData\Jenkins\.jenkins\workspace\loanadvisor-e2e\.env
   ```
   （实际路径以 Jenkins → 任务 → Workspace 为准）

```ini
DEVICE_NAME=你的adb设备ID
LOGIN_PHONE=9110001254
LOGIN_OTP=123456
CHROMEDRIVER_PATH=G:\chromedriver\chromedriver-win64\chromedriver.exe
DB_PASSWORD=真实数据库密码
```

### 方式 B：Jenkins Credentials 注入 DB 密码（企业推荐）

1. Credentials 添加 Secret text，ID：`loanadvisor-db-password`
2. 在 `Jenkinsfile` 的 `environment` 块增加：
   ```groovy
   DB_PASSWORD = credentials('loanadvisor-db-password')
   ```

**检查项：**

- [ ] 工作区存在 `.env` 且 DEVICE_NAME / DB_PASSWORD 已填
- [ ] `.env` 从未提交到 GitHub

---

## 阶段 5：每次构建执行流程

### 5.1 构建前（必做）

```powershell
# 终端 1：确认手机在线
adb devices

# 终端 2：启动 Appium（保持运行）
appium
```

浏览器可访问：`http://127.0.0.1:4723/status` → 应返回 OK。

### 5.2 Jenkins 触发构建

1. 打开任务 `loanadvisor-e2e`
2. **Build with Parameters**

| 参数 | 首次建议 | 说明 |
|------|----------|------|
| RUN_E2E | ✅ 勾选 | 执行 `python run.py` 完整链路 |
| RUN_PYTEST | ❌ 不勾 | 稳定后再开 |
| SKIP_PREFLIGHT | ❌ 不勾 | 会跳过 adb/Appium 检查 |
| DEVICE_NAME_OVERRIDE | 留空 | 留空则用 `.env` |
| LOGIN_PHONE_OVERRIDE | 留空 | 临时换号时填写 |
| PLATFORM_VERSION_OVERRIDE | 留空 | 临时换 Android 版本 |
| APP_PACKAGE_OVERRIDE | 留空 | 临时换包名 |

3. 点击 **Build**

### 5.3 预期 Pipeline 阶段

```
Init → Checkout → Setup Python → Preflight → E2E → (Pytest E2E) → Allure Report → 归档
```

### 5.4 构建产物

任务页 **Build Artifacts** 可下载：

- `artifacts/login_result.json`
- `kyc_*.png`、`after_*.png`
- `reports/allure-results/`
- `reports/allure-report/`（需安装 Allure CLI）

**检查项：**

- [ ] Console Output 无 Preflight 报错
- [ ] E2E 阶段 exit code 0
- [ ] Artifacts 可下载截图与 login_result.json

---

## 阶段 6：日常开发闭环

```powershell
# 1. 改备份脚本业务逻辑后同步到框架
cd C:\Users\Win\PycharmProjects\pythonProject\loanadvisor_automation
python scripts\split_from_backup.py

# 2. 本地验证
venv\Scripts\activate
$env:PYTHONPATH="src"
python run.py

# 3. 提交推送
git add .
git status
git commit -m "feat: 描述你的改动"
git push origin main

# 4. Jenkins → Build with Parameters
```

**检查项：**

- [ ] split 后 `flows/kyc_router.py` 未被覆盖（手写文件）
- [ ] 本地 run.py 通过后再 push
- [ ] Jenkins 构建通过

---

## 阶段 7：可选增强

### 7.1 定时 nightly 构建

Jenkins 任务 → **Build Triggers** → **Build periodically**：

```
H 2 * * *
```

（每天凌晨 2 点左右）

### 7.2 GitHub Webhook 自动触发

1. Jenkins 安装 **GitHub plugin**
2. 任务 → **Build Triggers** → **GitHub hook trigger for GITScm polling**
3. GitHub 仓库 → Settings → Webhooks → Payload URL：
   ```
   http://YOUR_JENKINS:8080/github-webhook/
   ```

### 7.3 专用 Jenkins Agent

多台测试机时，在 `Jenkinsfile` 顶部改为：

```groovy
pipeline {
    agent { label 'appium-android' }
    // ...
}
```

每台 Agent 节点配置相同 label，并独立维护 `.env`。

---

## 常见问题速查

| 现象 | 处理 |
|------|------|
| Preflight：没有 Android 设备 | Jenkins 改登录用户；手机 USB 调试授权 |
| Preflight：Appium 未启动 | 先 `appium`；检查 4723 端口 |
| 找不到 run.py | Script Path 应为 `Jenkinsfile`（独立仓库） |
| pip 安装极慢 | 使用精简版 `requirements.txt` |
| DB 连接失败 | 检查工作区 `.env` 或 Jenkins Credentials |
| 配置改了不生效 | 改 Jenkins **工作区**里的 `.env`，不是 env.example |
| git push 被拒 | 检查 PAT 权限或 SSH key |

---

## 快速命令汇总（复制区）

```powershell
# --- 本地初始化 ---
cd C:\Users\Win\PycharmProjects\pythonProject\loanadvisor_automation
scripts\setup_windows.bat
notepad .env
adb devices
appium
venv\Scripts\python run.py

# --- 首次 push GitHub ---
git init
git add .
git status
git commit -m "Initial commit: Loan Advisor Appium E2E automation framework"
git branch -M main
git remote add origin https://github.com/YOUR_ORG/loanadvisor-automation.git
git push -u origin main

# --- 日常推送 ---
git add .
git commit -m "feat: your change"
git push origin main
```

---

相关文档：

- 本地 Jenkins 详细说明：`docs/JENKINS_LOCAL_SETUP.md`
- 项目 README：`README.md`
- 业务流程说明：上级目录 `appium自动化测试_业务说明.md`
