export type ClipboardTextWriteResult =
  | { ok: true; method: "clipboard" | "execCommand" }
  | { ok: false; reason: "empty" | "unsupported" | "denied" | "error"; error?: unknown };

async function queryClipboardWritePermission(): Promise<PermissionState | null> {
  if (typeof navigator === "undefined" || !navigator.permissions?.query) {
    return null;
  }

  try {
    const status = await navigator.permissions.query({
      name: "clipboard-write" as PermissionName,
    });
    return status.state;
  } catch {
    return null;
  }
}

function writeTextWithExecCommand(text: string): boolean {
  if (typeof document === "undefined" || !document.execCommand) {
    return false;
  }

  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "true");
  textArea.style.position = "fixed";
  textArea.style.top = "0";
  textArea.style.left = "-9999px";
  textArea.style.opacity = "0";

  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();
  textArea.setSelectionRange(0, text.length);

  try {
    return document.execCommand("copy");
  } finally {
    textArea.remove();
  }
}

export async function writeTextToClipboard(
  text: string,
): Promise<ClipboardTextWriteResult> {
  if (!text) {
    return { ok: false, reason: "empty" };
  }

  const permission = await queryClipboardWritePermission();
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return { ok: true, method: "clipboard" };
    }
  } catch (error) {
    if (writeTextWithExecCommand(text)) {
      return { ok: true, method: "execCommand" };
    }
    return {
      ok: false,
      reason: permission === "denied" ? "denied" : "error",
      error,
    };
  }

  if (writeTextWithExecCommand(text)) {
    return { ok: true, method: "execCommand" };
  }

  return {
    ok: false,
    reason: permission === "denied" ? "denied" : "unsupported",
  };
}
