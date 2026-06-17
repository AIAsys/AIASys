# AIASys Windows Shell 环境快速验证脚本
# 运行方式（管理员非必须）：
#   powershell -ExecutionPolicy Bypass -File verify-windows-shell-env.ps1
#
# 作用：检测当前 Windows 上 Git Bash / WSL / busybox-w32 / PowerShell / CMD / Git 的可用性，
#       并尝试运行 busybox-w32 的一个简单命令，验证 fallback 是否可行。

param(
    [string]$BusyboxPath = "$env:LOCALAPPDATA\aiasys\tools\busybox-w32\busybox.exe"
)

function Test-CommandAvailable {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        return @{ available = $true; path = $cmd.Source }
    }
    return @{ available = $false; path = $null }
}

function Find-GitBash {
    # 优先从 git.exe 推断 Git Bash 真实路径
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        $gitRoot = Split-Path (Split-Path $git.Source -Parent) -Parent
        $candidates = @(
            Join-Path $gitRoot "bin\bash.exe"
            Join-Path $gitRoot "usr\bin\bash.exe"
        )
        foreach ($c in $candidates) {
            if (Test-Path $c) { return $c }
        }
    }
    # 常见安装路径
    @(
        "$env:ProgramFiles\Git\bin\bash.exe"
        "$env:ProgramFiles\Git\usr\bin\bash.exe"
        "${env:ProgramFiles(x86)}\Git\bin\bash.exe"
        "${env:ProgramFiles(x86)}\Git\usr\bin\bash.exe"
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}

$gitBashPath = Find-GitBash

$results = [ordered]@{
    git_bash = @{ available = [bool]$gitBashPath; path = $gitBashPath }
    wsl      = (Test-CommandAvailable wsl)
    git      = (Test-CommandAvailable git)
    pwsh     = (Test-CommandAvailable pwsh)
    powershell = (Test-CommandAvailable powershell)
    cmd      = (Test-CommandAvailable cmd)
}

Write-Host "=== AIASys Windows Shell 环境检测结果 ===" -ForegroundColor Cyan
foreach ($name in $results.Keys) {
    $r = $results[$name]
    $status = if ($r.available) { "✅ 可用" } else { "❌ 不可用" }
    Write-Host "$($name.PadRight(12)): $status" -NoNewline
    if ($r.path) {
        Write-Host "  ($($r.path))" -ForegroundColor DarkGray
    } else {
        Write-Host
    }
}

# 推荐层级（与 ShellExecutor 一致）：Git Bash -> WSL -> busybox -> PowerShell -> CMD
$recommended = $null
if ($results.git_bash.available) {
    $recommended = "Git Bash (posix)"
} elseif ($results.wsl.available) {
    $recommended = "WSL"
} elseif (Test-Path $BusyboxPath) {
    $recommended = "busybox-w32"
} elseif ($results.pwsh.available) {
    $recommended = "PowerShell"
} elseif ($results.powershell.available) {
    $recommended = "PowerShell"
} else {
    $recommended = "CMD"
}
Write-Host "`n推荐 Shell: $recommended" -ForegroundColor Green

if (Test-Path $BusyboxPath) {
    Write-Host "`n正在测试 busybox-w32 ($BusyboxPath) ..." -ForegroundColor Cyan
    try {
        $output = & $BusyboxPath sh -c "echo ok; uname -o" 2>&1
        Write-Host "busybox-w32 输出："
        $output | ForEach-Object { Write-Host "  $_" }
    } catch {
        Write-Host "busybox-w32 运行失败：$_" -ForegroundColor Red
    }
} else {
    Write-Host "`n未找到 busybox-w32：$BusyboxPath" -ForegroundColor Yellow
    Write-Host "可在 AIASys 桌面端「全局设置 -> 环境增强 -> busybox-w32」中自动下载。" -ForegroundColor Yellow
}
