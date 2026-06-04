; AIASys Desktop NSIS 自定义脚本
; 由 electron-builder 自动包含

; ==================== 安装前 ====================

!macro customInit
  ; 安装前检测应用窗口是否正在运行（FindWindow 为 NSIS 内置指令，无需插件）
  FindWindow $R0 "" "AIASys Desktop"
  IntCmp $R0 0 continueInstall

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

!macro customUnWelcomePage
  ; 卸载欢迎页：询问是否删除用户数据
  !insertmacro MUI_UNPAGE_WELCOME
!macroend

; 在卸载文件后、完成页前插入数据清理确认
!macro customRemoveFiles
  MessageBox MB_YESNO|MB_ICONQUESTION "是否同时删除用户数据（工作区文件、会话历史、日志、本地数据库）？" IDYES deleteData IDNO keepData
  deleteData:
    RMDir /r "$APPDATA\AIASys Desktop"
    DetailPrint "已删除用户数据"
    Goto dataDone
  keepData:
    DetailPrint "保留用户数据"
  dataDone:
!macroend
