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