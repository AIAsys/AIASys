import type { WorkspaceTab } from "./components/WorkspaceTabBar";

export type SplitDirection = "horizontal" | "vertical";

export interface PaneLeaf {
  kind: "leaf";
  id: string;
  tabs: WorkspaceTab[];
  activeTabId: string | null;
}

export interface SplitNode {
  kind: "split";
  id: string;
  direction: SplitDirection;
  children: [PaneTreeNode, PaneTreeNode];
  sizes: [number, number];
}

export type PaneTreeNode = PaneLeaf | SplitNode;

// ---- factories ----

let _leafCounter = 0;
function newLeafId(): string {
  return `leaf-${++_leafCounter}`;
}

let _splitCounter = 0;
function newSplitId(): string {
  return `split-${++_splitCounter}`;
}

let _tabCloneCounter = 0;
function cloneTabForSplit(tab: WorkspaceTab): WorkspaceTab {
  return {
    ...tab,
    id: `${tab.id}:split-${++_tabCloneCounter}`,
  };
}

export function createRootLeaf(): PaneLeaf {
  _leafCounter = 0;
  _splitCounter = 0;
  _tabCloneCounter = 0;
  return { kind: "leaf", id: "main", tabs: [], activeTabId: null };
}

export function createLeaf(
  tabs: WorkspaceTab[] = [],
  activeTabId: string | null = null,
): PaneLeaf {
  return { kind: "leaf", id: newLeafId(), tabs, activeTabId };
}

// ---- tree queries ----

export function findLeaf(
  tree: PaneTreeNode,
  leafId: string,
): PaneLeaf | null {
  if (tree.kind === "leaf") {
    return tree.id === leafId ? tree : null;
  }
  return findLeaf(tree.children[0], leafId) ?? findLeaf(tree.children[1], leafId);
}

export function findLeafWithTab(
  tree: PaneTreeNode,
  tabId: string,
): PaneLeaf | null {
  if (tree.kind === "leaf") {
    return tree.tabs.some((t) => t.id === tabId) ? tree : null;
  }
  return (
    findLeafWithTab(tree.children[0], tabId) ??
    findLeafWithTab(tree.children[1], tabId)
  );
}

export function getAllLeafIds(tree: PaneTreeNode): string[] {
  if (tree.kind === "leaf") return [tree.id];
  return [...getAllLeafIds(tree.children[0]), ...getAllLeafIds(tree.children[1])];
}

/** Find the ancestor split that contains the given leaf as a direct child. */
export function findParentSplit(
  tree: PaneTreeNode,
  leafId: string,
): SplitNode | null {
  if (tree.kind === "leaf") return null;
  const [left, right] = tree.children;
  if (left.kind === "leaf" && left.id === leafId) return tree;
  if (right.kind === "leaf" && right.id === leafId) return tree;
  return findParentSplit(left, leafId) ?? findParentSplit(right, leafId);
}

// ---- tree mutations ----

/** Replace a node anywhere in the tree by ID (leaf or split). */
export function replaceNode(
  tree: PaneTreeNode,
  nodeId: string,
  newNode: PaneTreeNode,
): PaneTreeNode {
  if (tree.id === nodeId) return newNode;
  if (tree.kind === "leaf") return tree;
  const [left, right] = tree.children;
  const newLeft = replaceNode(left, nodeId, newNode);
  const newRight = replaceNode(right, nodeId, newNode);
  if (newLeft !== left || newRight !== right) {
    return { ...tree, children: [newLeft, newRight] };
  }
  return tree;
}

/** Update a specific leaf by ID. */
export function updateLeaf(
  tree: PaneTreeNode,
  leafId: string,
  updater: (leaf: PaneLeaf) => PaneLeaf,
): PaneTreeNode {
  if (tree.kind === "leaf") {
    if (tree.id === leafId) return updater(tree);
    return tree;
  }
  const [left, right] = tree.children;
  const newLeft = updateLeaf(left, leafId, updater);
  const newRight = updateLeaf(right, leafId, updater);
  if (newLeft !== left || newRight !== right) {
    return { ...tree, children: [newLeft, newRight] };
  }
  return tree;
}

/** Split a leaf, moving the given tab into a new adjacent leaf.
 *  When tabFirst=false (default), tab goes to the right/bottom child.
 *  When tabFirst=true, tab goes to the left/top child. */
export function splitLeaf(
  tree: PaneTreeNode,
  leafId: string,
  tabId: string,
  direction: SplitDirection,
  tabFirst = false,
): { tree: PaneTreeNode; newLeafId: string } {
  const leaf = findLeaf(tree, leafId);
  if (!leaf) return { tree, newLeafId: leafId };

  const tab = leaf.tabs.find((t) => t.id === tabId);
  if (!tab) return { tree, newLeafId: leafId };

  const sourceTabs = leaf.tabs.filter((t) => t.id !== tabId);
  const sourceActiveId =
    leaf.activeTabId === tabId ? (sourceTabs[0]?.id ?? null) : leaf.activeTabId;

  const newLeaf = createLeaf([tab], tab.id);
  const sourceLeaf: PaneLeaf = {
    kind: "leaf",
    id: leaf.id,
    tabs: sourceTabs,
    activeTabId: sourceActiveId,
  };

  const children: [PaneTreeNode, PaneTreeNode] = tabFirst
    ? [newLeaf, sourceLeaf]
    : [sourceLeaf, newLeaf];

  const splitNode: SplitNode = {
    kind: "split",
    id: newSplitId(),
    direction,
    children,
    sizes: [50, 50],
  };

  return {
    tree: replaceNode(tree, leafId, splitNode),
    newLeafId: newLeaf.id,
  };
}

/** Split a leaf for toolbar actions.
 *  Multi-tab leaves move the selected tab into the new leaf so the previous
 *  tab remains visible. Single-tab leaves duplicate the tab to avoid creating
 *  an empty pane. */
export function splitLeafForToolbar(
  tree: PaneTreeNode,
  leafId: string,
  tabId: string,
  direction: SplitDirection,
  tabFirst = false,
): { tree: PaneTreeNode; newLeafId: string } {
  const leaf = findLeaf(tree, leafId);
  if (!leaf) return { tree, newLeafId: leafId };

  if (leaf.tabs.length !== 1) {
    return splitLeaf(tree, leafId, tabId, direction, tabFirst);
  }

  const tab = leaf.tabs.find((t) => t.id === tabId);
  if (!tab) return { tree, newLeafId: leafId };

  const clonedTab = cloneTabForSplit(tab);
  const newLeaf = createLeaf([clonedTab], clonedTab.id);
  const sourceLeaf: PaneLeaf = {
    ...leaf,
    activeTabId: tab.id,
  };
  const children: [PaneTreeNode, PaneTreeNode] = tabFirst
    ? [newLeaf, sourceLeaf]
    : [sourceLeaf, newLeaf];

  const splitNode: SplitNode = {
    kind: "split",
    id: newSplitId(),
    direction,
    children,
    sizes: [50, 50],
  };

  return {
    tree: replaceNode(tree, leafId, splitNode),
    newLeafId: newLeaf.id,
  };
}

/** Remove a tab from a leaf (does NOT prune). Use with pruneEmptyLeaves. */
export function removeTab(
  tree: PaneTreeNode,
  leafId: string,
  tabId: string,
): PaneTreeNode {
  return updateLeaf(tree, leafId, (leaf) => {
    const closingIdx = leaf.tabs.findIndex((t) => t.id === tabId);
    const nextTabs = leaf.tabs.filter((t) => t.id !== tabId);
    let nextActiveId = leaf.activeTabId;
    if (leaf.activeTabId === tabId) {
      nextActiveId =
        nextTabs[Math.min(closingIdx, nextTabs.length - 1)]?.id ?? null;
    }
    return { ...leaf, tabs: nextTabs, activeTabId: nextActiveId };
  });
}

/** Prune empty leaves: if a split has an empty leaf child, promote the sibling. */
export function pruneEmptyLeaves(tree: PaneTreeNode): PaneTreeNode {
  if (tree.kind === "leaf") return tree;

  const [left, right] = [
    pruneEmptyLeaves(tree.children[0]),
    pruneEmptyLeaves(tree.children[1]),
  ] as [PaneTreeNode, PaneTreeNode];

  if (left.kind === "leaf" && left.tabs.length === 0) return right;
  if (right.kind === "leaf" && right.tabs.length === 0) return left;

  if (left !== tree.children[0] || right !== tree.children[1]) {
    return { ...tree, children: [left, right] };
  }
  return tree;
}

/** Move a tab from one leaf to another, pruning if source becomes empty. */
export function moveTab(
  tree: PaneTreeNode,
  tabId: string,
  fromLeafId: string,
  toLeafId: string,
): PaneTreeNode {
  if (fromLeafId === toLeafId) return tree;

  const fromLeaf = findLeaf(tree, fromLeafId);
  const tab = fromLeaf?.tabs.find((t) => t.id === tabId);
  if (!tab) return tree;

  let result = removeTab(tree, fromLeafId, tabId);
  result = updateLeaf(result, toLeafId, (leaf) => ({
    ...leaf,
    tabs: [...leaf.tabs, tab],
    activeTabId: tab.id,
  }));
  result = pruneEmptyLeaves(result);
  return result;
}

/** Move a tab from one leaf to a target leaf, then split the target so the tab
 *  gets its own leaf. tabFirst controls whether the tab leaf is left/top or right/bottom. */
export function splitWithTab(
  tree: PaneTreeNode,
  tabId: string,
  fromLeafId: string,
  targetLeafId: string,
  direction: SplitDirection,
  tabFirst: boolean,
): { tree: PaneTreeNode; newLeafId: string } {
  // First move the tab to the target leaf
  const next = moveTab(tree, tabId, fromLeafId, targetLeafId);
  // Then split the target leaf
  const result = splitLeaf(next, targetLeafId, tabId, direction, tabFirst);
  return result;
}

/** Check if any leaf in the tree has tabs. */
export function hasAnyTabs(tree: PaneTreeNode): boolean {
  if (tree.kind === "leaf") return tree.tabs.length > 0;
  return hasAnyTabs(tree.children[0]) || hasAnyTabs(tree.children[1]);
}

/** Reorder tabs within a leaf. */
export function reorderTabs(
  tree: PaneTreeNode,
  leafId: string,
  fromIndex: number,
  toIndex: number,
): PaneTreeNode {
  return updateLeaf(tree, leafId, (leaf) => {
    const nextTabs = [...leaf.tabs];
    const [moved] = nextTabs.splice(fromIndex, 1);
    if (!moved) return leaf;
    nextTabs.splice(toIndex, 0, moved);
    return { ...leaf, tabs: nextTabs };
  });
}

/** Open a file (as a new tab) in a specific leaf. If a tab with the same
 *  name already exists in that leaf, activate it instead. */
export function openFileInLeaf(
  tree: PaneTreeNode,
  leafId: string,
  tab: WorkspaceTab,
): { tree: PaneTreeNode; tabId: string } {
  const leaf = findLeaf(tree, leafId);
  if (!leaf) return { tree, tabId: "" };

  const existingIndex = leaf.tabs.findIndex((t) => t.file?.name === tab.file?.name);
  if (existingIndex >= 0) {
    const existingTab = leaf.tabs[existingIndex];
    return {
      tree: updateLeaf(tree, leafId, (l) => ({ ...l, activeTabId: existingTab.id })),
      tabId: existingTab.id,
    };
  }

  const nextTree = updateLeaf(tree, leafId, (l) => ({
    ...l,
    tabs: [...l.tabs, tab],
    activeTabId: tab.id,
  }));
  return { tree: nextTree, tabId: tab.id };
}

/** Split a leaf and put the new tab in the new child leaf.
 *  tabFirst controls which side gets the new tab (left/top or right/bottom). */
export function splitLeafWithNewTab(
  tree: PaneTreeNode,
  leafId: string,
  tab: WorkspaceTab,
  direction: SplitDirection,
  tabFirst: boolean,
): { tree: PaneTreeNode; newLeafId: string; tabId: string } {
  const leaf = findLeaf(tree, leafId);
  if (!leaf) return { tree, newLeafId: leafId, tabId: "" };
  if (leaf.tabs.length === 0) {
    const result = openFileInLeaf(tree, leafId, tab);
    return { tree: result.tree, newLeafId: leafId, tabId: result.tabId };
  }

  // First add the tab to the target leaf
  const withTab = updateLeaf(tree, leafId, (leaf) => ({
    ...leaf,
    tabs: [...leaf.tabs, tab],
    activeTabId: tab.id,
  }));

  // Then split the leaf
  const result = splitLeaf(withTab, leafId, tab.id, direction, tabFirst);
  return { ...result, tabId: tab.id };
}
