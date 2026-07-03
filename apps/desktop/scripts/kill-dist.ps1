$ErrorActionPreference = 'SilentlyContinue'
$targetDir = Join-Path (Get-Location) "apps\desktop\dist\win-unpacked"
$targetZip = Join-Path (Get-Location) "apps\desktop\dist\AIASys-0.4.27-win.zip"

# 尝试通过 openfiles 查找占用
$output = openfiles /query /fo csv 2>$null | ConvertFrom-Csv
if ($output) {
    $output | Where-Object { $_.'Open File (PID\Status)' -like "*$targetDir*" -or $_.'Open File (PID\Status)' -like "*$targetZip*" } | ForEach-Object {
        $line = $_.'Open File (PID\Status)'
        if ($line -match '(\d+):') {
            $pid = $matches[1]
            Write-Host "Killing PID $pid"
            Stop-Process -Id $pid -Force
        }
    }
}

Start-Sleep -Seconds 2
if (Test-Path $targetDir) { Remove-Item $targetDir -Recurse -Force }
if (Test-Path $targetZip) { Remove-Item $targetZip -Force }
Write-Host "Cleanup done"
