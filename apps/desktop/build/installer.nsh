; AIASys Desktop NSIS 自定义脚本
; 由 electron-builder 自动包含

; ==================== 安装时 ====================

!macro customInstall
  ; 尝试开启 Windows 长路径支持（需要重启生效）
  ; 由于 package.json 使用 asInvoker，标准用户没有管理员权限，HKLM 写入会失败。
  ; 仅当实际拥有管理员权限时才写入，否则弹出提示引导用户手动启用。
  UserInfo::GetAccountType
  Pop $R1
  StrCmp $R1 "Admin" hasAdmin

  DetailPrint "当前未以管理员身份运行，跳过自动启用 Windows 长路径"
  MessageBox MB_OK|MB_ICONINFORMATION "AIASys Desktop 建议启用 Windows 长路径支持以获得最佳兼容性。$\n当前安装未以管理员身份运行，无法自动开启。$\n安装完成后可手动设置注册表：$\nHKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\FileSystem$\nLongPathsEnabled = 1（DWORD）$\n修改后需要重启系统生效。"

hasAdmin:
  WriteRegDWORD HKLM "SYSTEM\CurrentControlSet\Control\FileSystem" "LongPathsEnabled" 1
  DetailPrint "已启用 Windows 长路径支持（需要重启生效）"

longPathDone:
!macroend

; ==================== 安装前 ====================

!macro customInit
  ; 安装前检测应用窗口是否正在运行（FindWindow 为 NSIS 内置指令，无需插件）
  ; 窗口标题与 main.cjs 中 BrowserWindow.title 保持一致（带空格）
  FindWindow $R0 "" "AIASys Desktop"
  IntCmp $R0 0 checkProcess

  MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "AIASys Desktop 正在运行。安装前需要关闭该应用。点击确定自动关闭并继续安装，点击取消退出安装程序。" IDOK closeApp IDCANCEL cancelInstall

checkProcess:
  ; 安装前检测并终止正在运行的 AIASys Desktop 进程
  ; 使用 taskkill 替代 nsProcess 插件（CI 环境中 nsProcess 插件可能缺失）
  nsExec::ExecToStack 'tasklist /FI "IMAGENAME eq AIASys_Desktop.exe" 2>NUL | find /I "AIASys_Desktop.exe"'
  Pop $R0
  StrCmp $R0 "0" 0 continueInstall

  MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "AIASys Desktop 正在运行。安装前需要关闭该应用。点击确定自动关闭并继续安装，点击取消退出安装程序。" IDOK closeApp IDCANCEL cancelInstall

closeApp:
  nsExec::ExecToStack 'taskkill /F /IM "AIASys_Desktop.exe" 2>NUL'
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
    nsExec::ExecToStack 'taskkill /F /IM "AIASys_Desktop.exe" 2>NUL'
    Sleep 1000
  continueUninstall:
!macroend

; ==================== 卸载确认 ====================

!macro customUnInstall
  ; 在卸载文件完成后，询问是否删除用户数据
  ; 注意：用户数据目录名由 Electron app name（package.json 的 name 字段）决定，
  ; 实际为 aiasys-desktop，不是 productName（AIASys_Desktop），也不是带空格的 AIASys Desktop。
  MessageBox MB_YESNO|MB_ICONQUESTION "是否同时删除用户数据（工作区文件、会话历史、日志、本地数据库）？选择「是」将彻底删除 %APPDATA%\aiasys-desktop 下的所有数据。选择「否」仅卸载程序，保留用户数据。" IDYES deleteData IDNO keepData

deleteData:
  ; Electron 始终把用户数据写在 per-user 的 Roaming 下；卸载时强制切到 current 上下文，
  ; 避免 per-machine 安装时 $APPDATA 指向 ProgramData 而漏删。
  SetShellVarContext current
  RMDir /r "$APPDATA\aiasys-desktop"
  DetailPrint "已删除用户数据"
  Goto dataDone

keepData:
  DetailPrint "保留用户数据"

dataDone:
!macroend
