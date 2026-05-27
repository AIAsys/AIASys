# scripts/

项目级工具脚本目录，按用途分为三个子目录。

## 子目录

| 目录 | 用途 |
|------|------|
| `dev/` | 开发环境脚本，含 `dev.sh` 统一入口、生命周期测试等 |
| `design/` | 设计基线校验与 CSS 导出 |
| `security/` | 安全扫描脚本 |

## 常用入口

```bash
./dev.sh              # 启动前后端开发服务
./dev.sh design-lint  # 视觉设计基线校验
./dev.sh status       # 查看服务状态
```