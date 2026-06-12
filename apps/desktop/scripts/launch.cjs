const path = require("path");
const { spawn } = require("child_process");

// 在 require("electron") 之前设置环境变量，
// 让 electron 包直接使用 dist 目录，避免读取可能带换行的 path.txt
const electronDistDir = path.resolve(__dirname, "..", "node_modules", "electron", "dist");
process.env.ELECTRON_OVERRIDE_DIST_PATH = electronDistDir;

const electronBinary = require("electron");

const mode = process.argv[2] || "dev";
const desktopRoot = path.resolve(__dirname, "..");
const mainEntry = path.join(desktopRoot, "src", "main.cjs");
const extraArgs = (process.env.AIASYS_DESKTOP_ELECTRON_ARGS || "")
  .split(/\s+/)
  .map((value) => value.trim())
  .filter(Boolean);

const child = spawn(electronBinary, [mainEntry, ...extraArgs], {
  cwd: desktopRoot,
  detached: process.platform !== "win32",
  stdio: ["inherit", "inherit", "inherit", "ipc"],
  env: {
    ...process.env,
    AIASYS_DESKTOP_MODE: mode,
  },
});

let shutdownStarted = false;
let forcedExitTimer = null;
let requestedExitCode = null;

function stopChild(reason = "SIGTERM") {
  if (shutdownStarted || child.exitCode !== null) {
    return;
  }
  shutdownStarted = true;
  requestedExitCode = reason === "SIGINT" ? 130 : 0;

  if (process.platform === "win32") {
    const killer = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
      stdio: "ignore",
    });
    killer.once("exit", () => process.exit(requestedExitCode ?? 0));
    killer.once("error", () => process.exit(requestedExitCode ?? 0));
    return;
  }

  if (child.connected) {
    try {
      child.send({ type: "shutdown", reason });
    } catch {
      // ignore and fall back to a hard kill timer below
    }
  }

  forcedExitTimer = setTimeout(() => {
    if (child.exitCode !== null) {
      return;
    }
    try {
      process.kill(-child.pid, "SIGKILL");
    } catch {
      process.exit(requestedExitCode ?? 0);
    }
  }, 5000);
}

process.once("SIGINT", () => {
  stopChild("SIGINT");
});

process.once("SIGTERM", () => {
  stopChild("SIGTERM");
});

child.on("exit", (code) => {
  if (forcedExitTimer) {
    clearTimeout(forcedExitTimer);
    forcedExitTimer = null;
  }
  process.exit(requestedExitCode ?? code ?? 0);
});

child.on("error", (error) => {
  console.error("[aiasys-desktop] electron launch failed:", error);
  process.exit(1);
});
