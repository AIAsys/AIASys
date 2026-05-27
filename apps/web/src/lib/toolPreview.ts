export interface ToolPreviewData {
  toolName: string;
  toolParams?: Record<string, unknown>;
  toolOutput?: string;
  taskId?: string;
  triggerRect?: DOMRect;
}

export interface ToolPreviewEventLike {
  type?: string;
  tool_call_id?: string | null;
  tool_name?: string | null;
  arguments?: unknown;
  content?: unknown;
  output?: unknown;
  stdout?: unknown;
  stderr?: unknown;
  message?: unknown;
  return_value?: unknown;
}

function stringifyPreviewValue(value: unknown): string {
  if (value == null) {
    return "";
  }

  if (typeof value === "string") {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map((item) => stringifyPreviewValue(item)).join("");
  }

  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }

  return String(value);
}

function pushUniqueSection(sections: string[], nextValue: string) {
  const normalized = nextValue.trim();
  if (!normalized) {
    return;
  }

  if (!sections.includes(normalized)) {
    sections.push(normalized);
  }
}

export function parseToolParams(
  rawParams: unknown,
): Record<string, unknown> | undefined {
  if (rawParams == null) {
    return undefined;
  }

  if (typeof rawParams === "string") {
    const trimmed = rawParams.trim();
    if (!trimmed) {
      return undefined;
    }

    try {
      const parsed = JSON.parse(trimmed) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
      return { value: parsed };
    } catch {
      return { raw: rawParams };
    }
  }

  if (Array.isArray(rawParams)) {
    return { items: rawParams };
  }

  if (typeof rawParams === "object") {
    return rawParams as Record<string, unknown>;
  }

  return { value: rawParams };
}

export function extractToolOutput(rawEvent: Partial<ToolPreviewEventLike>): string | undefined {
  const sections: string[] = [];

  pushUniqueSection(
    sections,
    stringifyPreviewValue(rawEvent.content ?? rawEvent.output),
  );

  if (rawEvent.return_value && typeof rawEvent.return_value === "object") {
    const returnValue = rawEvent.return_value as Record<string, unknown>;
    pushUniqueSection(sections, stringifyPreviewValue(returnValue.output));
    pushUniqueSection(sections, stringifyPreviewValue(returnValue.message));
  }

  const stdout = stringifyPreviewValue(rawEvent.stdout).trim();
  const stderr = stringifyPreviewValue(rawEvent.stderr).trim();
  if (stdout) {
    pushUniqueSection(sections, stdout);
  }
  if (stderr) {
    pushUniqueSection(
      sections,
      stdout ? `[stderr]\n${stderr}` : stderr,
    );
  }

  pushUniqueSection(sections, stringifyPreviewValue(rawEvent.message));

  if (sections.length === 0) {
    return undefined;
  }

  return sections.join("\n\n");
}

export function resolveToolPreviewFromEvents(
  events: ToolPreviewEventLike[],
  toolCallId: string,
) {
  let toolName: string | undefined;
  let toolParams: Record<string, unknown> | undefined;
  const outputs: string[] = [];

  for (const event of events) {
    if (event.tool_call_id !== toolCallId) {
      continue;
    }

    if (event.type === "tool_call") {
      toolName =
        typeof event.tool_name === "string" && event.tool_name.trim()
          ? event.tool_name
          : toolName;
      toolParams = parseToolParams(event.arguments) ?? toolParams;
      continue;
    }

    if (event.type === "tool_result") {
      toolName =
        typeof event.tool_name === "string" && event.tool_name.trim()
          ? event.tool_name
          : toolName;
      const output = extractToolOutput(event);
      if (output) {
        pushUniqueSection(outputs, output);
      }
    }
  }

  return {
    toolName: toolName || toolCallId,
    toolParams,
    toolOutput: outputs.length > 0 ? outputs.join("\n\n") : undefined,
  };
}
