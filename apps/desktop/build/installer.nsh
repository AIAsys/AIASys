; AIASys Desktop NSIS 自定义脚本
; 由 electron-builder 自动包含

; ==================== 安装时 ====================

!macro customInstall
  ; 开启 Windows 长路径支持（需要重启生效）
  WriteRegDWORD HKLM "SYSTEM\CurrentControlSet\Control\FileSystem" "LongPathsEnabled" 1
!macroend

; ==================== 安装前 ====================

!macro customInit
  ; 安装前检测应用窗口是否正在运行（FindWindow 为 NSIS 内置指令，无需插件）
  FindWindow $R0 "" "AIASys Desktop"
  IntCmp $R0 0 checkProcess

  MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "AIASys Desktop 正在运行。安装前需要关闭该应用。点击确定自动关闭并继续安装，点击取消退出安装程序。" IDOK closeApp IDCANCEL cancelInstall

checkProcess:
  ; 安装前检测并终止正在运行的 AIASys Desktop 进程
  ; 使用 taskkill 替代 nsProcess 插件（CI 环境中 nsProcess 插件可能缺失）
  nsExec::ExecToStack 'tasklist /FI "IMAGENAME eq AIASys Desktop.exe" 2>NUL | find /I "AIASys Desktop.exe"'
  Pop $R0
  StrCmp $R0 "0" 0 continueInstall

  MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "AIASys Desktop 正在运行。安装前需要关闭该应用。点击确定自动关闭并继续安装，点击取消退出安装程序。" IDOK closeApp IDCANCEL cancelInstall

closeApp:
  nsExec::ExecToStack 'taskkill /F /IM "AIASys Desktop.exe" 2>NUL'
  Sleep 2000
  Goto continueInstall

cancelInstall:
  Quit

continueInstall:
!macroend

; ==================== 卸载前 ====================

!macro customUnInit
  ; 卸载前检测并终止正在运行的 AIASys Desktop 进程
  FindWindow $R0 "" "AIASys Desktop"
  IntCmp $R0 0 continueUninstall
    nsExec::ExecToStack 'taskkill /F /IM "AIASys Desktop.exe" 2>NUL'
    Sleep 1000
  continueUninstall:
!macroend

; ==================== 卸载确认 ====================

!macro customUnInstall
  ; 在卸载文件完成后，询问是否删除用户数据
  MessageBox MB_YESNO|MB_ICONQUESTION "是否同时删除用户数据（工作区文件、会话历史、日志、本地数据库）？选择「是」将彻底删除 %APPDATA%\AIASys Desktop 下的所有数据。选择「否」仅卸载程序，保留用户数据。" IDYES deleteData IDNO keepData

deleteData:
  RMDir /r "$APPDATA\AIASys Desktop"
  DetailPrint "已删除用户数据"
  Goto dataDone

keepData:
  DetailPrint "保留用户数据"

dataDone:
!macroend
