# AIASys Markdown Output Guide

## 功能

定义 AIASys 前端特殊 Markdown 语法的完整规范，包括：

- ECharts 交互式图表引用（`:::aiasys-file` directive + `type="echarts"`）
- CSV 表格预览（`type="csv"`）
- 图片引用（`type="image"`）
- 数学公式（行内 `$` / 块级 `$$`）
- Mermaid 流程图
- 资源引用统一协议（展示路径 vs 相对路径、禁止 http(s) 链接包装）

## 使用场景

主控需要在最终回复中展示图表、表格、图片或流程图时，通过 `LoadSkill` 加载以获取完整语法规范。

## 维护说明

- 本 skill 纯为 Markdown 输出格式规范，不包含工具调用逻辑
- 若前端新增或修改 directive 类型，同步更新本文件
