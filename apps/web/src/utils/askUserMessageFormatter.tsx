import React from "react";

/**
 * 格式化消息内容，支持简单的列表显示
 */
export function formatMessage(message: string): React.ReactNode {
  if (!message) return null;

  // 统一 CRLF/孤立 CR 为 LF，避免 Windows 来源的消息分段失败
  const normalized = message.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

  const hasBulletList = normalized.includes("\n- ") || normalized.startsWith("- ");
  const hasNumberList = /^\d+\./.test(normalized) || normalized.includes("\n1.");

  if (!hasBulletList && !hasNumberList) {
    const paragraphs = normalized.split("\n\n");
    if (paragraphs.length === 1) return <span>{normalized}</span>;

    return (
      <div className="space-y-2">
        {/* key={index} is safe — static text transform, paragraphs never reorder */}
        {paragraphs.map((paragraph, index) => (
          <p key={index} className="mb-2">
            {paragraph}
          </p>
        ))}
      </div>
    );
  }

  const lines = normalized.split("\n");
  const elements: React.ReactNode[] = [];
  let currentList: string[] = [];
  let listType: "bullet" | "number" | null = null;

  const flushList = () => {
    if (currentList.length === 0) return;

    const ListTag = listType === "bullet" ? "ul" : "ol";
    const listClass =
      listType === "bullet"
        ? "list-disc list-inside space-y-1 my-2 ml-2"
        : "list-decimal list-inside space-y-1 my-2 ml-2";

    elements.push(
      <ListTag key={`list-${elements.length}`} className={listClass}>
        {/* key={index} is safe — static text transform, list items never reorder */}
        {currentList.map((item, index) => (
          <li key={index} className="text-sm text-muted-foreground">
            {item}
          </li>
        ))}
      </ListTag>,
    );

    currentList = [];
    listType = null;
  };

  lines.forEach((line, index) => {
    const trimmedLine = line.trim();

    if (trimmedLine.startsWith("- ")) {
      if (listType && listType !== "bullet") flushList();
      listType = "bullet";
      currentList.push(trimmedLine.substring(2));
      return;
    }

    if (/^\d+\.\s/.test(trimmedLine)) {
      if (listType && listType !== "number") flushList();
      listType = "number";
      currentList.push(trimmedLine.replace(/^\d+\.\s/, ""));
      return;
    }

    if (currentList.length > 0) flushList();
    if (trimmedLine) {
      elements.push(
        <p key={`text-${index}`} className="mb-2">
          {trimmedLine}
        </p>,
      );
    }
  });

  flushList();
  return <div>{elements}</div>;
}
