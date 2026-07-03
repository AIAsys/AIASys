$ErrorActionPreference = 'SilentlyContinue'
$procs = Get-Process | Where-Object { $_.Path -like '*AIASys*' -or $_.Name -like '*AIASys*' -or $_.Name -like '*electron*' }
foreach ($p in $procs) {
    Write-Host "Found: $($p.Name) (PID $($p.Id)) - $($p.Path)"
    Stop-Process -Id $p.Id -Force
    Write-Host "Killed PID $($p.Id)"
}
Write-Host "Done"
