import { WORKSPACE_FOLDER_MARKER_FILENAME } from "@/utils/fileTreeUtils";

interface WorkspaceAssetFileLike {
  name: string;
}

interface AssetTreeNodeLike {
  node_type?: string;
  children?: AssetTreeNodeLike[];
}

function normalizeAssetPath(path: string): string {
  return path.replace(/\\/g, "/").replace(/^\/+/, "").trim();
}

function isFolderMarkerPath(path: string): boolean {
  return (
    normalizeAssetPath(path).split("/").filter(Boolean).pop() ===
    WORKSPACE_FOLDER_MARKER_FILENAME
  );
}

export function countWorkspaceAssetEntries(files: WorkspaceAssetFileLike[]) {
  const directoryPaths = new Set<string>();
  let fileCount = 0;

  files.forEach((file) => {
    const normalizedPath = normalizeAssetPath(file.name);
    if (!normalizedPath) {
      return;
    }

    const parts = normalizedPath.split("/").filter(Boolean);
    const isMarker = isFolderMarkerPath(normalizedPath);
    const folderDepth = parts.length - 1;

    for (let index = 1; index <= folderDepth; index += 1) {
      directoryPaths.add(parts.slice(0, index).join("/"));
    }

    if (!isMarker) {
      fileCount += 1;
    }
  });

  return {
    fileCount,
    directoryCount: directoryPaths.size,
  };
}

export function countAssetTreeEntries(nodes: AssetTreeNodeLike[]) {
  let fileCount = 0;
  let directoryCount = 0;

  const visit = (node: AssetTreeNodeLike) => {
    if (node.node_type === "directory") {
      directoryCount += 1;
      node.children?.forEach(visit);
      return;
    }

    fileCount += 1;
  };

  nodes.forEach(visit);

  return {
    fileCount,
    directoryCount,
  };
}
