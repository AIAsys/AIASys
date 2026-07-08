#!/usr/bin/env pwsh
# dev.ps1 -- AIASys 开发入口脚本（Windows PowerShell 版本）
# 功能与 dev.sh 对齐：启动前后端开发服务、查看状态、设计校验等。

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Command = "start",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"

$PROJECT_ROOT = $PSScriptRoot
$FRONTEND_PORT = if ($env:AIASYS_FRONTEND_PORT) { $env:AIASYS_FRONTEND_PORT } else { 13000 }
$BACKEND_PORT = if ($env:AIASYS_BACKEND_PORT) { $env:AIASYS_BACKEND_PORT } else { 13001 }
$BACKEND_URL = "http://127.0.0.1:${BACKEND_PORT}"
$FRONTEND_URL = "http://127.0.0.1:${FRONTEND_PORT}"

function Print-Usage {
    Write-Host @"
Usage:
  .\dev.ps1              启动前后端开发服务
  .\dev.ps1 start        启动前后端开发服务
  .\dev.ps1 status       查看前后端端口与健康状态
  .\dev.ps1 design-lint  校验根目录 DESIGN.md
  .\dev.ps1 design-export-css [output]
                        从 DESIGN.md 生成 Tailwind 4 CSS 变量草案
  .\dev.ps1 design-export-runtime
                        生成当前运行时变量候选主题和映射说明
  .\dev.ps1 setup-hooks  启用仓库内置 Git hooks
"@
}

function Test-UrlReady {
    param([string]$Url)
    try {
        $null = Invoke-RestMethod -Uri $Url -Method GET -ErrorAction Stop -TimeoutSec 2
        return $true
    } catch {
        return $false
    }
}

# 端口探测：返回 $true 表示空闲，$false 表示被占用
function Test-PortFree {
    param([string]$HostName, [int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect($HostName, $Port)
        $client.Close()
        return $false  # 连接成功 = 被占用
    } catch {
        return $true   # 连接失败 = 空闲
    }
}

function Find-AvailablePort {
    param([string]$HostName, [int]$StartPort, [int]$Max = 200)
    for ($p = $StartPort; $p -lt $StartPort + $Max; $p++) {
        if (Test-PortFree -HostName $HostName -Port $p) {
            return $p
        }
    }
    return $null
}

function Start-Backend {
    param([int]$Port)
    $backendDir = Join-Path (Join-Path $PROJECT_ROOT "apps") "backend"
    $python = Join-Path (Join-Path (Join-Path $backendDir ".venv") "Scripts") "python.exe"
    if (-not (Test-Path $python)) {
        $python = Join-Path (Join-Path (Join-Path $backendDir ".venv") "bin") "python3"
    }
    $arguments = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$Port")
    return Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $backendDir -PassThru -WindowStyle Hidden
}

function Start-Frontend {
    param([int]$Port, [string]$ApiTarget)
    $frontendDir = Join-Path (Join-Path $PROJECT_ROOT "apps") "web"
    $env:VITE_API_TARGET = $ApiTarget
    $arguments = @("run", "dev", "--", "--host", "0.0.0.0", "--port", "$Port")
    return Start-Process -FilePath "npm" -ArgumentList $arguments -WorkingDirectory $frontendDir -PassThru -WindowStyle Hidden
}

function Invoke-Status {
    $frontendStatus = if (Test-UrlReady -Url "${FRONTEND_URL}/") { "up" } else { "down" }
    $backendStatus = if (Test-UrlReady -Url "${BACKEND_URL}/health") { "up" } else { "down" }

    Write-Host "frontend ${FRONTEND_URL}: ${frontendStatus}"
    Write-Host "backend  ${BACKEND_URL}: ${backendStatus}"

    if ($frontendStatus -eq "up" -and $backendStatus -eq "up") {
        exit 0
    }
    exit 1
}

function Invoke-Start {
    # 检查后端端口
    $backendLocked = [bool]$env:AIASYS_BACKEND_PORT
    if (-not (Test-PortFree -HostName "127.0.0.1" -Port $BACKEND_PORT)) {
        if ($backendLocked) {
            Write-Host "❌ 后端端口 ${BACKEND_PORT} 已被占用，且 AIASYS_BACKEND_PORT 已锁定" -ForegroundColor Red
            exit 1
        }
        $newBackendPort = Find-AvailablePort -HostName "127.0.0.1" -StartPort ($BACKEND_PORT + 1)
        if (-not $newBackendPort) {
            Write-Host "❌ 无法为后端找到可用端口（起始: ${BACKEND_PORT}）" -ForegroundColor Red
            exit 1
        }
        Write-Host "⚠ 后端端口 ${BACKEND_PORT} 被占用，自动切换到 ${newBackendPort}" -ForegroundColor Yellow
        $script:BACKEND_PORT = $newBackendPort
        $script:BACKEND_URL = "http://127.0.0.1:${newBackendPort}"
    }

    # 检查前端端口
    $frontendLocked = [bool]$env:AIASYS_FRONTEND_PORT
    if (-not (Test-PortFree -HostName "127.0.0.1" -Port $FRONTEND_PORT)) {
        if ($frontendLocked) {
            Write-Host "❌ 前端端口 ${FRONTEND_PORT} 已被占用，且 AIASYS_FRONTEND_PORT 已锁定" -ForegroundColor Red
            exit 1
        }
        $newFrontendPort = Find-AvailablePort -HostName "127.0.0.1" -StartPort ($FRONTEND_PORT + 1)
        if (-not $newFrontendPort) {
            Write-Host "❌ 无法为前端找到可用端口（起始: ${FRONTEND_PORT}）" -ForegroundColor Red
            exit 1
        }
        Write-Host "⚠ 前端端口 ${FRONTEND_PORT} 被占用，自动切换到 ${newFrontendPort}" -ForegroundColor Yellow
        $script:FRONTEND_PORT = $newFrontendPort
        $script:FRONTEND_URL = "http://127.0.0.1:${newFrontendPort}"
    }

    $backendProc = Start-Backend -Port $BACKEND_PORT
    $frontendProc = Start-Frontend -Port $FRONTEND_PORT -ApiTarget $BACKEND_URL

    Write-Host "backend  已启动 PID=$($backendProc.Id)  URL=$BACKEND_URL"
    Write-Host "frontend 已启动 PID=$($frontendProc.Id)  URL=$FRONTEND_URL"

    # 注册清理逻辑
    $cleanup = {
        param($BackendProc, $FrontendProc)
        if ($BackendProc -and -not $BackendProc.HasExited) {
            Stop-Process -Id $BackendProc.Id -Force -ErrorAction SilentlyContinue
        }
        if ($FrontendProc -and -not $FrontendProc.HasExited) {
            Stop-Process -Id $FrontendProc.Id -Force -ErrorAction SilentlyContinue
        }
    }

    try {
        while ($true) {
            Start-Sleep -Milliseconds 500
            if ($backendProc.HasExited -or $frontendProc.HasExited) {
                break
            }
        }
    } finally {
        & $cleanup -BackendProc $backendProc -FrontendProc $frontendProc
    }
}

function Invoke-BashScript {
    param([string]$ScriptPath, [string[]]$ScriptArgs)
    $bash = "C:\Program Files\Git\bin\bash.exe"
    if (-not (Test-Path $bash)) {
        $bash = "bash"
    }
    $allArgs = @($ScriptPath) + $ScriptArgs
    & $bash @allArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

switch ($Command.ToLower()) {
    "start" {
        Invoke-Start
    }
    "status" {
        Invoke-Status
    }
    "design-lint" {
        $scriptPath = Join-Path (Join-Path (Join-Path $PROJECT_ROOT "scripts") "design") "validate-design-md.sh"
        Invoke-BashScript -ScriptPath $scriptPath -ScriptArgs $Args
    }
    "design-export-css" {
        $scriptPath = Join-Path (Join-Path (Join-Path $PROJECT_ROOT "scripts") "design") "export-tailwind4-css.mjs"
        & node $scriptPath @Args
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    "design-export-runtime" {
        $scriptPath = Join-Path (Join-Path (Join-Path $PROJECT_ROOT "scripts") "design") "export-runtime-theme-candidate.mjs"
        & node $scriptPath @Args
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    "setup-hooks" {
        $scriptPath = Join-Path (Join-Path (Join-Path $PROJECT_ROOT "scripts") "dev") "setup-hooks.sh"
        Invoke-BashScript -ScriptPath $scriptPath -ScriptArgs $Args
    }
    { $_ -in "help", "-h", "--help" } {
        Print-Usage
    }
    default {
        Write-Host "Unknown command: ${Command}" -ForegroundColor Red
        Print-Usage
        exit 1
    }
}
