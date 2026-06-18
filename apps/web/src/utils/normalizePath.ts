/**
 * Normalize file path separators to forward slashes.
 * On Windows, paths may contain backslashes; this utility ensures consistent
 * forward-slash separators across platforms.
 *
 * TODO: Consider adopting this utility across all files that currently use
 * inline `.replace(/\\/g, "/")` calls.
 */
export function normalizePath(filePath: string): string {
  return filePath.replace(/\\/g, "/");
}

/**
 * Windows 文件名中禁止出现的字符（不含路径分隔符 / \，
 * 分隔符在调用前已由 normalizePath 统一为 /）。
 * 参考 Win32 文件命名规则：< > : " | ? *
 */
const WINDOWS_INVALID_FILENAME_CHARS = /[<>:"|?*]/;

/**
 * Windows 保留设备名，不能作为文件名使用。
 * 包括 CON、PRN、AUX、NUL、COM1-9、LPT1-9（不区分大小写）。
 */
const WINDOWS_RESERVED_NAMES = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.|$)$/i;

/**
 * 校验工作区路径在 Windows 上是否合法。
 *
 * 逐段（以 / 分隔）检查每个路径片段：
 * - 不含 Windows 非法字符 < > : " | ? *
 * - 不以点号或空格结尾（Windows 不允许）
 * - 不是 Windows 保留设备名（CON、PRN、NUL 等）
 *
 * @param normalizedPath 已经过 normalizePath 处理的正斜杠路径
 * @returns 校验失败时返回错误消息，校验通过返回 null
 */
export function validateWindowsFilePath(normalizedPath: string): string | null {
  const segments = normalizedPath.split("/").filter((s) => s.length > 0);
  for (const segment of segments) {
    // 检查非法字符
    const charMatch = segment.match(WINDOWS_INVALID_FILENAME_CHARS);
    if (charMatch) {
      return `文件名包含 Windows 不允许的字符 "${charMatch[0]}"`;
    }
    // 检查以点号或空格结尾
    if (/[.\s]$/.test(segment)) {
      return `文件名不能以点号或空格结尾："${segment}"`;
    }
    // 检查 Windows 保留设备名
    if (WINDOWS_RESERVED_NAMES.test(segment)) {
      return `"${segment}" 是 Windows 保留名称，不能用作文件名`;
    }
  }
  return null;
}
