@echo off
setlocal
cd /d "%~dp0.."

echo === Loan Advisor Automation - Windows 初始化 ===

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 python，请先安装 Python 3.10+
    exit /b 1
)

if not exist venv\Scripts\python.exe (
    echo 创建虚拟环境 venv ...
    python -m venv venv
)

call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

if not exist .env (
    copy /Y config\env.example .env
    echo.
    echo [重要] 已生成 .env ，请用记事本编辑以下内容后保存:
    echo   - DEVICE_NAME   （adb devices 看到的设备 ID）
    echo   - LOGIN_PHONE / LOGIN_OTP
    echo   - CHROMEDRIVER_PATH（如路径不存在可留空，使用 Appium 自动下载）
    echo   - DB_PASSWORD
)

echo.
echo === 初始化完成 ===
echo 下一步:
echo   1. 编辑 .env
echo   2. 手机 USB 连接，执行 adb devices
echo   3. 另开终端: appium
echo   4. 本目录执行: venv\Scripts\python run.py
echo.
echo Jenkins 本地部署说明见: docs\JENKINS_LOCAL_SETUP.md

endlocal
