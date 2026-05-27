/**
 * TreeNode memo comparator 单元测试（Node.js 独立运行）
 *
 * 运行: node src/components/layout/WorkspaceSidebar/__tests__/TreeNodeMemo.test.mjs
 */

import assert from "node:assert";

function getFileSelectionKey(filename) {
  return `file:${filename}`;
}

function getFolderSelectionKey(path) {
  return `folder:${path}`;
}

function getTreeNodeSelectionKey(node) {
  return node.isDirectory
    ? getFolderSelectionKey(node.path)
    : getFileSelectionKey(node.file?.name ?? node.path);
}

// 当前实现（修复后）
function treeNodeMemoEqual(prev, next) {
  if (prev.node !== next.node) return false;
  if (prev.level !== next.level) return false;
  if (prev.sessionId !== next.sessionId) return false;
  if (prev.token !== next.token) return false;

  const prevExpanded = prev.expandedFolders.has(prev.node.path);
  const nextExpanded = next.expandedFolders.has(next.node.path);
  if (prevExpanded !== nextExpanded) return false;

  const prevKey = getTreeNodeSelectionKey(prev.node);
  const nextKey = getTreeNodeSelectionKey(next.node);
  const prevSelected = prev.selectedItemKeys.has(prevKey);
  const nextSelected = next.selectedItemKeys.has(nextKey);
  if (prevSelected !== nextSelected) return false;

  const prevDragOver = prev.dragOverFolder === prev.node.path;
  const nextDragOver = next.dragOverFolder === next.node.path;
  if (prevDragOver !== nextDragOver) return false;
  const prevDragging = prev.draggingNode === prev.node.path;
  const nextDragging = next.draggingNode === prev.node.path;
  if (prevDragging !== nextDragging) return false;

  const prevLoading = prev.loadingDirectoryPath === prev.node.path;
  const nextLoading = next.loadingDirectoryPath === prev.node.path;
  if (prevLoading !== nextLoading) return false;

  if (prev.imageIndexMap.size !== next.imageIndexMap.size) return false;
  for (const [key, val] of prev.imageIndexMap) {
    if (next.imageIndexMap.get(key) !== val) return false;
  }

  return true;
}

// 旧实现（修复前）
function treeNodeMemoEqualOld(prev, next) {
  if (prev.node !== next.node) return false;
  if (prev.level !== next.level) return false;
  if (prev.sessionId !== next.sessionId) return false;
  if (prev.token !== next.token) return false;

  const prevExpanded = prev.expandedFolders.has(prev.node.path);
  const nextExpanded = next.expandedFolders.has(next.node.path);
  if (prevExpanded !== nextExpanded) return false;
  const isExpandedBranch = prev.node.isDirectory && (prevExpanded || nextExpanded);
  if (isExpandedBranch && prev.expandedFolders !== next.expandedFolders) {
    return false;
  }

  const prevKey = getTreeNodeSelectionKey(prev.node);
  const nextKey = getTreeNodeSelectionKey(next.node);
  const prevSelected = prev.selectedItemKeys.has(prevKey);
  const nextSelected = next.selectedItemKeys.has(nextKey);
  if (prevSelected !== nextSelected) return false;
  if (isExpandedBranch && prev.selectedItemKeys !== next.selectedItemKeys) {
    return false;
  }

  const prevDragOver = prev.dragOverFolder === prev.node.path;
  const nextDragOver = next.dragOverFolder === prev.node.path;
  if (prevDragOver !== nextDragOver) return false;
  const prevDragging = prev.draggingNode === prev.node.path;
  const nextDragging = prev.draggingNode === prev.node.path;
  if (prevDragging !== nextDragging) return false;
  if (
    isExpandedBranch &&
    (prev.dragOverFolder !== next.dragOverFolder ||
      prev.draggingNode !== next.draggingNode)
  ) {
    return false;
  }

  const prevLoading = prev.loadingDirectoryPath === prev.node.path;
  const nextLoading = prev.loadingDirectoryPath === prev.node.path;
  if (prevLoading !== nextLoading) return false;
  if (isExpandedBranch && prev.loadingDirectoryPath !== next.loadingDirectoryPath) {
    return false;
  }

  if (prev.imageIndexMap !== next.imageIndexMap) return false;

  return true;
}

function makeBaseProps() {
  return {
    node: { path: "/docs", name: "docs", isDirectory: true },
    level: 1,
    sessionId: "sess-1",
    token: "tk",
    imageIndexMap: new Map([["a.png", 0]]),
    expandedFolders: new Set(["/docs"]),
    selectedItemKeys: new Set(),
    dragOverFolder: null,
    draggingNode: null,
    loadingDirectoryPath: null,
  };
}

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`✅ ${name}`);
    passed++;
  } catch (e) {
    console.log(`❌ ${name}`);
    console.log(`   ${e.message}`);
    failed++;
  }
}

test("expandedFolders 引用变化但当前节点状态不变 → 新 true, 旧 false", () => {
  const prev = makeBaseProps();
  const next = { ...prev, expandedFolders: new Set(["/docs", "/src"]) };
  assert.strictEqual(treeNodeMemoEqual(prev, next), true);
  assert.strictEqual(treeNodeMemoEqualOld(prev, next), false);
});

test("selectedItemKeys 引用变化但当前节点未选中 → 新 true, 旧 false", () => {
  const prev = makeBaseProps();
  const next = { ...prev, selectedItemKeys: new Set(["file:main.py"]) };
  assert.strictEqual(treeNodeMemoEqual(prev, next), true);
  assert.strictEqual(treeNodeMemoEqualOld(prev, next), false);
});

test("dragOverFolder 变化但当前节点不受影响 → 新 true, 旧 false", () => {
  const prev = makeBaseProps();
  const next = { ...prev, dragOverFolder: "/src" };
  assert.strictEqual(treeNodeMemoEqual(prev, next), true);
  assert.strictEqual(treeNodeMemoEqualOld(prev, next), false);
});

test("imageIndexMap 新实例但内容相同 → 新 true, 旧 false", () => {
  const prev = makeBaseProps();
  const next = { ...prev, imageIndexMap: new Map([["a.png", 0]]) };
  assert.strictEqual(treeNodeMemoEqual(prev, next), true);
  assert.strictEqual(treeNodeMemoEqualOld(prev, next), false);
});

test("imageIndexMap 内容变化 → 新旧都 false", () => {
  const prev = makeBaseProps();
  const next = { ...prev, imageIndexMap: new Map([["a.png", 1]]) };
  assert.strictEqual(treeNodeMemoEqual(prev, next), false);
  assert.strictEqual(treeNodeMemoEqualOld(prev, next), false);
});

test("当前节点展开状态变化 → 新旧都 false", () => {
  const prev = makeBaseProps();
  const next = { ...prev, expandedFolders: new Set() };
  assert.strictEqual(treeNodeMemoEqual(prev, next), false);
  assert.strictEqual(treeNodeMemoEqualOld(prev, next), false);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
