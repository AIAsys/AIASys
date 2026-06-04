const EXECUTION_DETAIL_TOOL_NAMES = new Set([
  "LocalIPythonBox",
  "IPythonBox",
  "Shell",
  "ReadFile",
  "WriteFile",
  "StrReplaceFile",
  "ReadMediaFile",
  "Grep",
  "Glob",
  "SearchWeb",
  "FetchURL",
]);

type ExecutionRecordSeed = {
  language: "python" | "bash";
  code: string;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

export function shouldTrackExecutionFlowTool(
  toolName: string | null | undefined,
): boolean {
  return EXECUTION_DETAIL_TOOL_NAMES.has(toolName || "");
}

export function getExecutionRecordSeed(
  toolName: string | null | undefined,
  rawArgs: unknown,
): ExecutionRecordSeed | null {
  const args = asRecord(rawArgs);
  if (!args) {
    return null;
  }

  if (toolName === "LocalIPythonBox" || toolName === "IPythonBox") {
    const code = typeof args.code === "string" ? args.code.trim() : "";
    if (!code) {
      return null;
    }
    return {
      language: "python",
      code,
    };
  }

  if (toolName === "Shell") {
    const command = typeof args.command === "string" ? args.command.trim() : "";
    if (!command) {
      return null;
    }
    return {
      language: "bash",
      code: command,
    };
  }

  return null;
}
