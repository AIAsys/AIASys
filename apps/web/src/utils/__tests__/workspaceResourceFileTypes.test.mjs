/**
 * workspaceResourceFileTypes 单元测试（Node.js 独立运行）
 *
 * 运行: node --experimental-strip-types src/utils/__tests__/workspaceResourceFileTypes.test.mjs
 */

import assert from "node:assert";

const moduleUrl = new URL("../workspaceResourceFileTypes.ts", import.meta.url);
const { inferWorkspaceResourceFileType } = await import(moduleUrl.href);

const cases = [
  [".aiasys/memory/workspace_memory.md", "memory"],
  ["global_workspace/.aiasys/.memory/MEMORY.md", "memory"],
  ["global_workspace/.aiasys/.memory/memory_summary.md", "memory"],
  ["global_workspace/.aiasys/.memory/raw_memories.md", "memory"],
  [".aiasys/.memory/rollout_summaries/2026-05-19-followup.md", "memory"],
  ["resources/graphs/project.kg", "graph"],
  ["datasets/demo.table.duckdb", "data_table"],
  ["connectors/demo.sqlite", "database"],
];

for (const [name, expected] of cases) {
  assert.strictEqual(
    inferWorkspaceResourceFileType({ name }),
    expected,
    `${name} 应识别为 ${expected}`,
  );
}

assert.strictEqual(
  inferWorkspaceResourceFileType({ name: "notes/ordinary.md" }),
  null,
  "普通 Markdown 文件不应被识别为 memory 资源",
);

console.log(`${cases.length + 1} passed`);
