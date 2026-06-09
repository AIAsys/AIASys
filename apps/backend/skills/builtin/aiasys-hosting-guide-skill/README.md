# AIASys Hosting Guide

## 功能

定义 AIASys 托管控制工具（`ControlWorkspaceHosting`）的完整使用指南，包括：

- 工具参数约束（enable / enable_and_check / pause / resume / stop）
- 托管用户指令（`<HOSTING_INSTRUCTION>`）的识别与响应规则
- 终止信号（`<TASK_DONE>`）的处理

## 使用场景

当主控需要启用、暂停、恢复或停止托管模式时，通过 `LoadSkill` 加载以获取完整操作指南。

## 维护说明

- 本 skill 纯为托管控制语义规范，不包含工具调用逻辑
- 若托管控制协议或指令格式变更，同步更新本文件
