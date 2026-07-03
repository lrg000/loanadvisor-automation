# 本地 Jenkins 新手上手（Windows）

本文档帮助你在**本机**把 `loanadvisor_automation` 跑在 Jenkins 上。  
**不需要修改** `appium自动化测试_备份.py`。

---

## 一、你需要准备什么

| 项目 | 说明 |
|------|------|
| Windows 10/11 | 与现在开发环境一致即可 |
| Python 3.10+ | 已加入 PATH |
| Android 手机 | USB 调试已开启 |
| adb | Android Platform Tools |
| Appium 2.x | `npm install -g appium` 后执行 `appium driver install uiautomator2` |
| Java 17+ | Jenkins 需要 |
| Jenkins LTS | 本机安装 |

---

## 二、一次性：初始化项目

在 PowerShell 或 CMD 中：

```bat
cd C:\Users\Win\PycharmProjects\pythonProject\loanadvisor_automation
scripts\setup_windows.bat
notepad .env
```

编辑 `.env` 里至少这几项：

```ini
DEVICE_NAME=你的adb设备ID
LOGIN_PHONE=测试手机号
LOGIN_OTP=123456
CHROMEDRIVER_PATH=你的chromedriver路径
DB_PASSWORD=数据库密码
```

验证本机能否手动跑通（**先确保 Jenkins 之前能跑通**）：

```bat
adb devices
appium
```

另开一个终端：

```bat
cd loanadvisor_automation
venv\Scripts\python run.py
```

---

## 三、安装 Jenkins（本机）

### 1. 安装 Java

下载并安装 [Temurin JDK 17](https://adoptium.net/)，安装后命令行能执行 `java -version`。

### 2. 安装 Jenkins

1. 打开 https://www.jenkins.io/download/
2. 下载 **Windows** 安装包（`.msi`）并安装
3. 安装过程中会提示设置**管理员密码**，记到 `initialAdminPassword` 文件里
4. 浏览器打开 http://localhost:8080
5. 安装推荐插件（**Pipeline** 必选）

### 3. 关键：Jenkins 要能访问 adb 和手机

Jenkins 默认以 **Windows 服务**运行，可能看不到你 USB 连接的手机。

**推荐做法（新手）**：让 Jenkins 以**当前登录用户**运行

1. `Win + R` → 输入 `services.msc`
2. 找到 **Jenkins** 服务 → 右键 **属性**
3. **登录** 选项卡 → 选「此账户」→ 填你的 Windows 用户名和密码
4. 重启 Jenkins 服务

改完后，用**同一用户**登录 Windows，连接手机，在 CMD 里 `adb devices` 能看到设备，Jenkins 构建才大概率成功。

---

## 四、创建 Jenkins Pipeline 任务

### 方式 A：Git 仓库（推荐）

若整个 `pythonProject` 已在 Git 中：

1. Jenkins 首页 → **新建任务**
2. 名称：`loanadvisor-e2e` → 选 **Pipeline** → 确定
3. **Pipeline** 区域：
   - Definition: **Pipeline script from SCM**
   - SCM: **Git**
   - Repository URL: 你的仓库地址（本地可先 push 到 GitHub/Gitee，或用 file 协议）
   - **Script Path**: `loanadvisor_automation/Jenkinsfile`（若仓库根是 pythonProject）  
     或 `Jenkinsfile`（若仓库根就是 loanadvisor_automation）
4. 保存

### 方式 B：不用 Git（最快试跑）

1. 新建 **Pipeline** 任务
2. Definition 选 **Pipeline script**
3. 把 `loanadvisor_automation/Jenkinsfile` 的全部内容粘贴进去
4. 在 Pipeline 最前面加一行固定工作目录（因为这种方式没有 checkout）：

在 Jenkins 任务配置里，**General** 勾选：

- **Restrict where this project can be run**（可选）

并在 **Pipeline** 脚本最上方 `pipeline {` 之前无法改 workspace，所以更简单的是：

**General → 高级 → 自定义工作空间**：

```
C:\Users\Win\PycharmProjects\pythonProject\loanadvisor_automation
```

然后 Pipeline script 粘贴 Jenkinsfile 内容即可（无需 Git checkout）。

---

## 五、每次构建前（必做）

Jenkins **不会**自动帮你常驻 Appium，需要：

1. 手机 USB 连接，`adb devices` 有 `device`
2. **单独开一个终端**运行：

```bat
appium
```

3. Jenkins 任务页 → **Build with Parameters**（或直接 **立即构建**）

### 构建参数说明

| 参数 | 建议 |
|------|------|
| RUN_E2E | 默认勾选，跑 `python run.py` |
| RUN_PYTEST | 首次可先不勾，跑通后再开 |
| SKIP_PREFLIGHT | 不要勾，除非你在调试 Pipeline 本身 |
| DEVICE_NAME_OVERRIDE | 留空用 `.env`；临时换机可填 adb 设备 ID |

---

## 六、构建成功后会看到什么

Console Output 大致顺序：

```
Init → Setup Python → Preflight → E2E → (Pytest) → 归档
```

构建完成后，任务页左侧 **Build Artifacts** 可下载：

- `artifacts/login_result.json`
- `reports/` 下截图、Allure 结果

---

## 七、常见问题

### 1. Preflight 报「没有在线 Android 设备」

- Jenkins 服务是否改成了你的 Windows 用户？
- 手机是否解锁、是否点了「允许 USB 调试」？
- 在**同一用户**下 CMD 执行 `adb devices` 是否有 `device`

### 2. Preflight 报「Appium 未启动」

先手动 `appium`，确认浏览器能打开 http://127.0.0.1:4723/status

### 3. 找不到 run.py

- 方式 B 请设置**自定义工作空间**为 `loanadvisor_automation` 目录
- 方式 A 检查 Script Path 是否正确

### 4. 配置改了没生效

改的是 `.env` 不是 `config/env.example`。Jenkins 工作区里的 `.env` 也要改。

### 5. DB 密码不想写在 .env

Jenkins → **Manage Jenkins → Credentials** 添加 Secret text，ID 如 `loanadvisor-db-password`。  
在 Jenkinsfile 的 `environment` 里加（需自行扩展）：

```groovy
DB_PASSWORD = credentials('loanadvisor-db-password')
```

本地新手阶段用 `.env` 即可。

---

## 八、日常开发流程（与备份脚本配合）

```
你在 appium自动化测试_备份.py 改逻辑
        ↓
python scripts/split_from_backup.py   （同步到框架）
        ↓
本地 venv\Scripts\python run.py 验证
        ↓
Jenkins 点构建
```

---

## 九、下一步（可选）

- 安装 Allure CLI，开启 `RUN_PYTEST` 生成 HTML 报告
- 配置 nightly 定时构建：`Build Triggers → Build periodically` → `H 2 * * *`
- 多台测试机：为 Jenkins Agent 打 label，Pipeline 里 `agent { label 'appium-android' }`
