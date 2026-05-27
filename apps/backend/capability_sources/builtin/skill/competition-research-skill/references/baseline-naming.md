# baseline 命名

竞赛项目里的 baseline 版本名同时是代码目录名、输出目录名、日志名前缀和实验索引 ID。名字不能只追求描述性，还要能排序、能被脚本校验、能让 AutoTask 稳定续跑。

## 统一格式

```text
{family}_b{NNN}_{slug}
```

示例：

- `lgb_b000_base`
- `lgb_b042_quantile_trigrid`
- `blend_b000_core`
- `catboost_b001_real`

字段含义：

| 字段 | 说明 |
|------|------|
| `family` | 模型或方法家族，只用小写英文和数字，如 `lgb`、`blend`、`catboost` |
| `bNNN` | family 内三位递增编号，从 `b000` 开始 |
| `slug` | 本轮核心变化，只用小写英文、数字和下划线 |

## 文件系统约束

同一轮实验必须使用同一个 version：

- `baselines/<version>/`
- `outputs/<version>/`
- `outputs/submissions/<version>/`
- `outputs/logs/<version>.log`
- `experiments[index].version`

如果项目 runner 额外生成指标文件，也使用同一个 version 作为目录或文件前缀。

## 新版本生成

先看当前可信主线所属 family，再生成下一个编号：

```bash
python3 scripts/baseline_names.py --mode next --family lgb --slug pairranker_on_trigrid
```

启动 runner 前校验：

```bash
python3 scripts/baseline_names.py --mode validate --workspace <workspace-root> --experiments experiments/index.json
```

## 旧项目整理

AIASys 当前处于 0-1 阶段，整理历史项目时不做旧名兼容。直接把旧目录名、实验索引、输出目录、日志名和 README 引用改成新格式。

清理后不保留 `legacy_version`、旧名映射文件或旧名别名。当前事实源只承认新 version。

不要继续创建 `v27`、`final_v2`、`new_idea` 这类目录。

## AutoTask 规则

AutoTask 每轮开始前必须先确定本轮唯一 version，并检查同名目录和日志：

1. 运行 `baseline_names.py --mode next` 或按同一规则手动生成 version。
2. 运行 `experiment.py --mode preflight --version <version>`。
3. 只有 preflight 通过后才复制 baseline 和启动 runner。

如果候选 version 不符合格式，当前轮直接暂停或改名，不要继续运行。
