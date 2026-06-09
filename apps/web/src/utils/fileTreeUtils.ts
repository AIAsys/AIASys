/**
 * 文件树工具函数
 * 将扁平的文件列表转换为树形结构，支持文件夹展开/折叠
 */

import type { WorkspaceFile } from "@/types/task";

export const WORKSPACE_FOLDER_MARKER_FILENAME = "__aiasys_folder__.md";

/** 文件树节点 */
export interface FileTreeNode {
  /** 节点名称（文件名或文件夹名） */
  name: string;
  /** 完整路径 */
  path: string;
  /** 电脑真实文件系统绝对路径 */
  absolutePath?: string | null;
  /** 是否为目录 */
  isDirectory: boolean;
  /** 子节点（仅目录有） */
  children?: FileTreeNode[];
  /** 原始文件数据（仅文件有） */
  file?: WorkspaceFile;
  /** 目录下的文件数量 */
  fileCount?: number;
  /** 后端目录/资源元数据 */
  meta?: Record<string, unknown>;
}

export function isWorkspaceFolderMarkerFile(filename: string): boolean {
  return (
    filename.replace(/\\/g, "/").split("/").pop() ===
    WORKSPACE_FOLDER_MARKER_FILENAME
  );
}

/**
 * 判断文件是否为图片类型
 */
export function isImageFile(filename: string): boolean {
  const ext = filename.split(".").pop()?.toLowerCase();
  return ["png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico"].includes(
    ext || "",
  );
}

/**
 * 判断文件是否为表格类型
 */
export function isTableFile(filename: string): boolean {
  const ext = filename.split(".").pop()?.toLowerCase();
  return ["csv", "xlsx", "xls", "tsv"].includes(ext || "");
}

/**
 * 判断文件是否为代码类型
 */
export function isCodeFile(filename: string): boolean {
  const ext = filename.split(".").pop()?.toLowerCase();
  return [
    "py",
    "js",
    "ts",
    "tsx",
    "jsx",
    "html",
    "css",
    "json",
    "yaml",
    "yml",
    "md",
    "ipynb",
    "sh",
    "bat",
  ].includes(ext || "");
}

/**
 * 获取文件类型分类
 */
export function getFileCategory(
  filename: string,
): "image" | "table" | "code" | "other" {
  if (isImageFile(filename)) return "image";
  if (isTableFile(filename)) return "table";
  if (isCodeFile(filename)) return "code";
  return "other";
}

/**
 * 将扁平的文件列表转换为树形结构
 * @param files 扁平的文件列表
 * @returns 树形结构的根节点数组
 */
export function buildFileTree(files: WorkspaceFile[]): FileTreeNode[] {
  // 使用对象来存储目录结构，key 是完整路径
  const dirMap: Record<string, FileTreeNode> = {};
  const dirAbsolutePathMap: Record<string, string> = {};
  const rootNodes: FileTreeNode[] = [];

  // 按路径排序，确保父目录先被创建
  const sortedFiles = [...files].sort((a, b) => a.name.localeCompare(b.name));

  for (const file of sortedFiles) {
    // 统一路径分隔符：将 Windows 反斜杠转换为标准斜杠
    const normalizedPath = file.name.replace(/\\/g, "/");
    const parts = normalizedPath.split("/").filter(Boolean);
    
    // 跳过系统目录 .aiasys 下的文件
    if (parts[0] === ".aiasys") continue;
    
    const absolutePath = file.absolute_path ?? undefined;
    if (absolutePath && parts.length > 1) {
      const absoluteParts = absolutePath.replace(/\\/g, "/").split("/");
      for (let i = 0; i < parts.length - 1; i++) {
        const dirPath = parts.slice(0, i + 1).join("/");
        const parentOffset = parts.length - 1 - i;
        const dirAbsoluteParts = absoluteParts.slice(0, absoluteParts.length - parentOffset);
        const dirAbsolutePath = dirAbsoluteParts.join("/") || "/";
        if (dirAbsolutePath) {
          dirAbsolutePathMap[dirPath] = dirAbsolutePath;
        }
      }
    }

    if (parts.length === 1) {
      // 根目录下的文件
      rootNodes.push({
        name: parts[0],
        path: parts[0],
        absolutePath,
        isDirectory: false,
        file: file,
      });
    } else {
      // 确保所有父目录都存在
      let currentPath = "";
      for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i];
        const parentPath = currentPath;
        currentPath = currentPath ? `${currentPath}/${part}` : part;

        if (!dirMap[currentPath]) {
          const dirNode: FileTreeNode = {
            name: part,
            path: currentPath,
            absolutePath: dirAbsolutePathMap[currentPath],
            isDirectory: true,
            children: [],
          };
          dirMap[currentPath] = dirNode;

          // 添加到父节点或根节点
          if (parentPath && dirMap[parentPath]) {
            dirMap[parentPath].children!.push(dirNode);
          } else if (!parentPath) {
            rootNodes.push(dirNode);
          }
        }
      }

      // 添加文件到其父目录
      const fileName = parts[parts.length - 1];
      if (fileName === WORKSPACE_FOLDER_MARKER_FILENAME) {
        continue;
      }
      const parentDir = parts.slice(0, -1).join("/");
      const fileNode: FileTreeNode = {
        name: fileName,
        path: file.name,
        absolutePath,
        isDirectory: false,
        file: file,
      };

      if (dirMap[parentDir]) {
        dirMap[parentDir].children!.push(fileNode);
      }
    }
  }

  // 转换 Map 为数组并递归处理
  return sortNodes(rootNodes);
}

/**
 * 递归排序节点：目录在前，文件在后，同类型按名称排序
 */
function sortNodes(nodes: FileTreeNode[]): FileTreeNode[] {
  return nodes
    .map((node) => ({
      ...node,
      children: node.children ? sortNodes(node.children) : undefined,
      fileCount: node.children ? countFiles(node) : undefined,
    }))
    .sort((a, b) => {
      // 目录在前
      if (a.isDirectory && !b.isDirectory) return -1;
      if (!a.isDirectory && b.isDirectory) return 1;
      // 同类型按名称排序
      return a.name.localeCompare(b.name);
    });
}

/**
 * 统计目录下的文件数量
 */
function countFiles(node: FileTreeNode): number {
  if (!node.children) return 0;
  return node.children.reduce((count, child) => {
    if (child.isDirectory) {
      return count + countFiles(child);
    }
    return count + 1;
  }, 0);
}

/**
 * 在树中搜索匹配的节点
 * @param nodes 树节点数组
 * @param query 搜索关键词
 * @returns 过滤后的树（保留匹配节点及其父节点）
 */
export function filterFileTree(
  nodes: FileTreeNode[],
  query: string,
): FileTreeNode[] {
  if (!query.trim()) return nodes;

  const lowerQuery = query.toLowerCase();

  function filterNode(node: FileTreeNode): FileTreeNode | null {
    // 如果是文件，检查名称是否匹配
    if (!node.isDirectory) {
      return node.name.toLowerCase().includes(lowerQuery) ? node : null;
    }

    // 如果是目录，递归过滤子节点
    const filteredChildren = node.children
      ?.map(filterNode)
      .filter((n): n is FileTreeNode => n !== null);

    // 如果目录名匹配或有匹配的子节点，保留该目录
    if (
      node.name.toLowerCase().includes(lowerQuery) ||
      (filteredChildren && filteredChildren.length > 0)
    ) {
      return {
        ...node,
        children: filteredChildren || [],
        fileCount: filteredChildren?.reduce(
          (count, child) =>
            count + (child.isDirectory ? child.fileCount || 0 : 1),
          0,
        ),
      };
    }

    return null;
  }

  return nodes.map(filterNode).filter((n): n is FileTreeNode => n !== null);
}

/**
 * 展平后的树节点（用于虚拟滚动）
 */
export interface FlatTreeNode {
  node: FileTreeNode;
  level: number;
}

/**
 * 将树形结构按展开状态展平为列表
 * @param nodes 树节点数组
 * @param expandedFolders 已展开的文件夹路径集合
 * @param level 当前层级
 * @returns 展平后的节点列表
 */
export function flattenFileTree(
  nodes: FileTreeNode[],
  expandedFolders: Set<string>,
  level = 0,
): FlatTreeNode[] {
  const result: FlatTreeNode[] = [];
  for (const node of nodes) {
    result.push({ node, level });
    if (node.isDirectory && expandedFolders.has(node.path) && node.children) {
      result.push(...flattenFileTree(node.children, expandedFolders, level + 1));
      // heavy 目录且有更多内容，在子节点末尾插入加载更多占位
      if (
        node.meta?.heavy === true &&
        node.meta?.has_more === true
      ) {
        result.push({
          node: {
            name: "",
            path: `__load_more__:${node.path}`,
            isDirectory: false,
            meta: { __load_more_parent__: node.path, ...node.meta },
          },
          level: level + 1,
        });
      }
    }
  }
  return result;
}

/**
 * 判断节点是否为 heavy 目录的加载更多占位行
 */
export function isLoadMoreRow(node: FileTreeNode): boolean {
  return typeof node.meta?.__load_more_parent__ === "string";
}

/**
 * 获取加载更多占位行对应的父目录路径
 */
export function getLoadMoreParentPath(node: FileTreeNode): string | undefined {
  return node.meta?.__load_more_parent__ as string | undefined;
}

/**
 * 获取树中所有图片文件
 */
export function getImageFiles(nodes: FileTreeNode[]): WorkspaceFile[] {
  const images: WorkspaceFile[] = [];

  function traverse(node: FileTreeNode) {
    if (!node.isDirectory && node.file && isImageFile(node.name)) {
      images.push(node.file);
    }
    node.children?.forEach(traverse);
  }

  nodes.forEach(traverse);
  return images;
}

/**
 * 将全局资源节点转换为文件树节点
 */
export function convertGlobalResourceNodesToFileTreeNodes(
  nodes: Array<{
    name: string;
    path: string;
    absolute_path?: string | null;
    node_type?: string;
    resource_type?: string;
    meta?: Record<string, unknown>;
    children?: Array<unknown>;
  }>,
): FileTreeNode[] {
  return nodes.map((node) => ({
    name: node.name,
    path: node.path,
    absolutePath: node.absolute_path,
    isDirectory: node.node_type === "directory",
    children: node.children
      ? convertGlobalResourceNodesToFileTreeNodes(
          node.children as Array<{
            name: string;
            path: string;
            absolute_path?: string | null;
            node_type?: string;
            resource_type?: string;
            meta?: Record<string, unknown>;
            children?: Array<unknown>;
          }>,
        )
      : undefined,
    meta: node.meta,
    file:
      node.node_type !== "directory"
        ? {
            name: node.path,
            size: 0,
            mtime: "",
            absolute_path: node.absolute_path,
            resource_type: node.resource_type,
            meta: node.meta,
          }
        : undefined,
  }));
}
