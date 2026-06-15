/**
 * 生成 URL/文件名安全的短随机 ID。
 *
 * 默认 16 字符十六进制（64 bit），比 UUID 短 20 字符，用于 session/conversation
 * 等会进入文件路径的 ID，降低 Windows MAX_PATH 超限概率。
 */
export function generateShortId(byteLength = 8): string {
  const bytes = new Uint8Array(byteLength);
  if (typeof crypto !== "undefined" && "getRandomValues" in crypto) {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < byteLength; i++) {
      bytes[i] = (Math.random() * 256) | 0;
    }
  }
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
