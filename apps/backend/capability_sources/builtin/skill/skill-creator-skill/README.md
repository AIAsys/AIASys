# Skill 开发工作台

创建和优化 AIASys 系统内置 Skill 的完整工具链。无需外部 CLI，提供原生开发、测试和优化能力。

## 适用场景

- 从零创建新 skill
- 改进现有 skill 的 SKILL.md 或脚本
- 优化 skill 的 description 触发准确率
- 管理 skill 版本和打包部署

## 核心流程

1. 确定 skill 要解决的问题
2. 编写 SKILL.md 草稿
3. 设计测试用例并运行触发测试
4. 评估结果（定性 + 定量）
5. 根据反馈重写优化
6. 重复迭代直到满意
7. 打包最终版本

## 内置工具

- `skill_dev.py` — Skill 结构设计和脚本编写
- `trigger_test.py` — 触发准确率测试
- `improve_desc.py` — Description 自动优化
