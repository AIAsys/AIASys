#Requires -Version 5.1
<#
.SYNOPSIS
    安全删除文件或文件夹到回收站（使用.NET方法）
.DESCRIPTION
    使用 Microsoft.VisualBasic.FileIO 将文件或文件夹移动到回收站，而非永久删除。
    这是 PowerShell Remove-Item 的安全替代方案。
.PARAMETER Path
    要删除的文件或文件夹路径（支持相对路径和通配符）
.PARAMETER Force
    强制删除，不提示确认
.EXAMPLE
    .\safe-delete.ps1 "old-notes.md"
.EXAMPLE
    .\safe-delete.ps1 "*.tmp" -Force
.EXAMPLE
    safe-delete "C:\Temp\test-folder"
.NOTES
    Author: 筱可
    Version: 1.0.0
    Date: 2026-02-19
#>

[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [Parameter(Mandatory=$true, Position=0, ValueFromPipeline=$true)]
    [string[]]$Path,
    
    [Parameter()]
    [switch]$Force
)

begin {
    # 加载 .NET 程序集
    try {
        Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction Stop
    }
    catch {
        Write-Error "无法加载 Microsoft.VisualBasic 程序集。确保 .NET Framework 已安装。"
        exit 1
    }
    
    $deleteOption = [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
    $uiOption = [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs
    
    $successCount = 0
    $failCount = 0
}

process {
    foreach ($itemPath in $Path) {
        # 解析路径（支持相对路径）
        $resolvedPaths = Resolve-Path -Path $itemPath -ErrorAction SilentlyContinue
        
        if (-not $resolvedPaths) {
            Write-Warning "路径不存在: $itemPath"
            $failCount++
            continue
        }
        
        foreach ($resolvedPath in $resolvedPaths) {
            $fullPath = $resolvedPath.Path
            
            # 确认提示（除非使用 -Force）
            if (-not $Force -and -not $PSCmdlet.ShouldProcess($fullPath, "移动到回收站")) {
                continue
            }
            
            try {
                $item = Get-Item -LiteralPath $fullPath -ErrorAction Stop
                
                if ($item.PSIsContainer) {
                    # 删除文件夹
                    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(
                        $fullPath,
                        $uiOption,
                        $deleteOption
                    )
                    Write-Host "📁 已删除文件夹到回收站: $($item.Name)" -ForegroundColor Green
                }
                else {
                    # 删除文件
                    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
                        $fullPath,
                        $uiOption,
                        $deleteOption
                    )
                    Write-Host "📄 已删除文件到回收站: $($item.Name)" -ForegroundColor Green
                }
                
                $successCount++
            }
            catch {
                Write-Error "删除失败: $fullPath - $_"
                $failCount++
            }
        }
    }
}

end {
    Write-Host "" 
    Write-Host "删除完成: 成功 $successCount 项, 失败 $failCount 项" -ForegroundColor Cyan
    
    if ($successCount -gt 0) {
        Write-Host "💡 如需恢复，请从回收站还原" -ForegroundColor Yellow
    }
}
