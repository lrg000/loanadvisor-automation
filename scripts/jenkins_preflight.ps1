param(
    [string]$DeviceName = "",
    [string]$AppiumServer = $env:APPIUM_SERVER
)

$ErrorActionPreference = "Stop"

if (-not $AppiumServer) {
    $AppiumServer = "http://127.0.0.1:4723"
}

Write-Host "========== Jenkins Preflight =========="

Write-Host "[1/4] Python"
python --version

Write-Host "[2/4] adb devices"
$adb = Get-Command adb -ErrorAction SilentlyContinue
if (-not $adb) {
    throw "adb 不在 PATH 中。请安装 Android Platform Tools 并加入环境变量。"
}

$devicesOutput = adb devices
Write-Host $devicesOutput

$onlineDevices = @(
    $devicesOutput -split "`n" |
    Where-Object { $_ -match "`tdevice$" } |
    ForEach-Object { ($_ -split "`t")[0].Trim() }
)

if ($onlineDevices.Count -eq 0) {
    throw "没有在线 Android 设备。请 USB 连接手机、开启调试、并在手机上点「允许 USB 调试」。"
}

if ($DeviceName) {
    if ($onlineDevices -notcontains $DeviceName) {
        throw "参数/环境 DEVICE_NAME=$DeviceName 不在 adb devices 列表中: $($onlineDevices -join ', ')"
    }
    Write-Host "目标设备已连接: $DeviceName"
} else {
    Write-Host "已连接设备: $($onlineDevices -join ', ')（将使用 .env 中的 DEVICE_NAME）"
}

Write-Host "[3/4] Appium Server: $AppiumServer"
try {
    $statusUrl = "$AppiumServer/status"
    $resp = Invoke-WebRequest -Uri $statusUrl -UseBasicParsing -TimeoutSec 5
    Write-Host "Appium status OK: $($resp.StatusCode)"
} catch {
    throw @"
Appium 未启动或地址错误: $AppiumServer
请先在另一个终端执行: appium
然后再点 Jenkins「立即构建」
"@
}

Write-Host "[4/4] .env"
if (-not (Test-Path ".env")) {
    Write-Host "[WARN] 未找到 .env，Setup 阶段会从 env.example 复制，请确认 DEVICE_NAME / LOGIN_PHONE 等配置"
} else {
    Write-Host ".env 已存在"
}

Write-Host "========== Preflight 通过 =========="
