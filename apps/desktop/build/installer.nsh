; AIASys Desktop NSIS 自定义脚本
; 由 electron-builder 自动包含

; ==================== 安装前 ====================

!macro customInit
  ; 安装前检测并终止正在运行的 AIASys Desktop 进程
  nsProcess::FindProcess "AIASys Desktop.exe"
  Pop $R0
  ${If} $R0 == "1"
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "AIASys Desktop 正在运行。安装前需要关闭该应用。$
$
点击“确定”自动关闭并继续安装，点击“取消”退出安装程序。" IDOK closeApp IDCANCEL cancelInstall

    closeApp:
      nsProcess::KillProcess "AIASys Desktop.exe"
      Pop $R0
      Sleep 2000
      Goto continueInstall

    cancelInstall:
      Quit

    continueInstall:
  ${EndIf}
!macroend

; ==================== 卸载前 ====================

!macro customUnInit
  ; 卸载前检测并终止正在运行的 AIASys Desktop 进程
  nsProcess::FindProcess "AIASys Desktop.exe"
  Pop $R0
  ${If} $R0 == "1"
    nsProcess::KillProcess "AIASys Desktop.exe"
    Pop $R0
    Sleep 1000
  ${EndIf}
!macroend

; ==================== 卸载确认 ====================

!macro customUnWelcomePage
  ; 卸载欢迎页：询问是否删除用户数据
  !insertmacro MUI_UNPAGE_WELCOME
!macroend

; 在卸载文件后、完成页前插入数据清理确认
!macro customRemoveFiles
  ; 询问是否删除用户数据目录
  MessageBox MB_YESNO|MB_ICONQUESTION "是否同时删除用户数据？$
$
用户数据包括：$
- 工作区文件和配置$
- 会话历史$
- 日志文件$
- 本地数据库$
$
数据目录: $APPDATA\AIASys Desktop$
$
点击“是”删除所有用户数据，点击“否”保留数据。" IDYES deleteData IDNO keepData

  deleteData:
    RMDir /r "$APPDATA\AIASys Desktop"
    Goto dataDone

  keepData:
    DetailPrint "保留用户数据"

  dataDone:
!macroend
