const fs = require("fs");
const path = require("path");

const desktopRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(desktopRoot, "..", "..");
const runtimeRoot = path.join(desktopRoot, ".dist");
const webStageRoot = path.join(runtimeRoot, "web");
const backendStageRoot = path.join(runtimeRoot, "backend");
const backendRoot = path.join(repoRoot, "apps", "backend");
const webRoot = path.join(repoRoot, "apps", "web");

function ensureExists(targetPath, label) {
  if (!fs.existsSync(targetPath)) {
    throw new Error(`${label} 不存在: ${targetPath}`);
  }
}

function resetDir(targetPath) {
  fs.rmSync(targetPath, { recursive: true, force: true });
  fs.mkdirSync(targetPath, { recursive: true });
}

function copyPath(sourcePath, targetPath, options = {}) {
  ensureExists(sourcePath, "source");
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  fs.cpSync(sourcePath, targetPath, {
    recursive: true,
    preserveTimestamps: true,
    ...options,
  });
}

function copyPathIfExists(sourcePath, targetPath, options = {}) {
  if (!fs.existsSync(sourcePath)) {
    console.warn(`[aiasys-desktop] 跳过不存在的路径: ${sourcePath}`);
    return;
  }
  copyPath(sourcePath, targetPath, options);
}

function prepareWebRuntime() {
  const webDistRoot = path.join(webRoot, "dist");

  ensureExists(webDistRoot, "web dist");

  copyPath(webDistRoot, path.join(webStageRoot, "dist"));
}

function prepareBackendRuntime() {
  const requiredEntries = [
    ".venv",
    "app",
    "vendor",
    "skills",
    "agent_runtime_helpers",
    "templates",
    "capability_sources",
    "pyproject.toml",
    "__init__.py",
  ];

  const optionalEntries = [
    "config.json",
    "config.example.json",
    "scripts",
    "fonts",
    "docs",
  ];

  for (const entry of requiredEntries) {
    copyPath(path.join(backendRoot, entry), path.join(backendStageRoot, entry));
  }

  for (const entry of optionalEntries) {
    copyPathIfExists(path.join(backendRoot, entry), path.join(backendStageRoot, entry));
  }

  // config.json 不在仓库中时，用 config.example.json 兜底
  const stagedConfigPath = path.join(backendStageRoot, "config.json");
  const stagedExamplePath = path.join(backendStageRoot, "config.example.json");
  if (!fs.existsSync(stagedConfigPath) && fs.existsSync(stagedExamplePath)) {
    fs.copyFileSync(stagedExamplePath, stagedConfigPath);
    console.warn("[aiasys-desktop] config.json 不存在，已从 config.example.json 复制");
  }

  fs.mkdirSync(path.join(backendStageRoot, "data", "workspaces"), { recursive: true });
  fs.mkdirSync(path.join(backendStageRoot, "logs"), { recursive: true });
  fs.mkdirSync(path.join(backendStageRoot, "workspaces"), { recursive: true });
}

function main() {
  resetDir(runtimeRoot);
  prepareWebRuntime();
  prepareBackendRuntime();
  console.log(`[aiasys-desktop] runtime prepared at ${runtimeRoot}`);
}

main();
