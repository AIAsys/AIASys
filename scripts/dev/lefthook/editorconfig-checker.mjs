#!/usr/bin/env node
/**
 * 跨平台 editorconfig-checker 包装器。
 *
 * Lefthook 在 Windows 上无法直接执行 bash 的 `|| true`，且 shell 转义行为不一致。
 * 本脚本接收 {staged_files} 参数列表，调用 npx editorconfig-checker，
 * 对非零退出码仅打印警告而不阻塞提交（与原有 `|| true` 语义一致）。
 */
import { spawnSync } from "node:child_process";

const excludePattern = "\\.git|node_modules|\\.venv|dist|\\.pytest_cache|\\.ruff_cache";
const files = process.argv.slice(2).filter(Boolean);

if (files.length === 0) {
  process.exit(0);
}

const result = spawnSync(
  "npx",
  ["editorconfig-checker", "-exclude", excludePattern, ...files],
  { stdio: "inherit", windowsHide: true },
);

if (result.status !== 0) {
  console.warn("[editorconfig-checker] 检查未通过，但按当前策略不阻塞提交。");
}
process.exit(0);
