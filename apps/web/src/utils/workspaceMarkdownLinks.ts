export type WorkspaceMarkdownLinkScope = "workspace" | "global";

export interface WorkspaceMarkdownReference {
  scope: WorkspaceMarkdownLinkScope;
  path: string;
  suffix: string;
}

interface ResolveWorkspaceMarkdownReferenceOptions {
  currentFileName?: string;
  currentScope?: WorkspaceMarkdownLinkScope;
}

const SCOPED_PREFIXES: Array<{
  prefix: string;
  scope: WorkspaceMarkdownLinkScope;
}> = [
  { prefix: "/workspace/", scope: "workspace" },
  { prefix: "workspace/", scope: "workspace" },
  { prefix: "./workspace/", scope: "workspace" },
  { prefix: "/global/", scope: "global" },
  { prefix: "global/", scope: "global" },
  { prefix: "./global/", scope: "global" },
];

function splitPathAndSuffix(value: string): { path: string; suffix: string } {
  const queryIndex = value.indexOf("?");
  const hashIndex = value.indexOf("#");
  const suffixIndex = [queryIndex, hashIndex]
    .filter((index) => index >= 0)
    .sort((left, right) => left - right)[0];

  if (suffixIndex === undefined) {
    return { path: value, suffix: "" };
  }

  return {
    path: value.slice(0, suffixIndex),
    suffix: value.slice(suffixIndex),
  };
}

function normalizeRelativePath(value: string): string {
  const parts: string[] = [];
  for (const part of value.replace(/\\/g, "/").split("/")) {
    if (!part || part === ".") {
      continue;
    }
    if (part === "..") {
      parts.pop();
      continue;
    }
    parts.push(part);
  }
  return parts.join("/");
}

function resolveRelativePath(baseFileName: string, rawPath: string): string {
  const normalizedBase = normalizeRelativePath(baseFileName);
  const baseParts = normalizedBase.split("/").filter(Boolean);
  baseParts.pop();
  return normalizeRelativePath([...baseParts, rawPath].join("/"));
}

function decodePath(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function stripSameOriginUrl(value: string): string | null {
  if (!/^[a-z][a-z0-9+.-]*:/i.test(value)) {
    return value;
  }

  if (!/^https?:/i.test(value) || typeof window === "undefined") {
    return null;
  }

  try {
    const parsed = new URL(value);
    if (parsed.origin !== window.location.origin) {
      return null;
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return null;
  }
}

export function resolveWorkspaceMarkdownReference(
  href?: string,
  options: ResolveWorkspaceMarkdownReferenceOptions = {},
): WorkspaceMarkdownReference | null {
  const rawHref = String(href ?? "")
    .trim()
    .replace(/^<|>$/g, "")
    .replace(/\\/g, "/");

  if (!rawHref || rawHref.startsWith("#")) {
    return null;
  }

  const sameOriginHref = stripSameOriginUrl(rawHref);
  if (!sameOriginHref) {
    return null;
  }

  const { path: rawPath, suffix } = splitPathAndSuffix(sameOriginHref);
  const path = decodePath(rawPath.trim());
  if (!path) {
    return null;
  }

  const lowerPath = path.toLowerCase();
  for (const { prefix, scope } of SCOPED_PREFIXES) {
    if (lowerPath.startsWith(prefix)) {
      const scopedPath = normalizeRelativePath(path.slice(prefix.length));
      return scopedPath ? { scope, path: scopedPath, suffix } : null;
    }
  }

  if (path.startsWith("/")) {
    return null;
  }

  if (!options.currentFileName) {
    return null;
  }

  const relativePath = resolveRelativePath(options.currentFileName, path);
  if (!relativePath) {
    return null;
  }

  return {
    scope: options.currentScope ?? "workspace",
    path: relativePath,
    suffix,
  };
}
