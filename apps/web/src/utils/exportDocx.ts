import {
  AlignmentType,
  BorderStyle,
  Document,
  ExternalHyperlink,
  HeadingLevel,
  ImageRun,
  Packer,
  Paragraph,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} from "docx";
import { saveAs } from "file-saver";
import MarkdownIt from "markdown-it";
import { apiFetch } from "@/lib/api/httpClient";
import { stripApiBaseUrl } from "./urlUtils";

// ... existing imports

// 定义 Token 类型
interface MdToken {
  type: string;
  tag: string;
  content: string;
  children: MdToken[] | null;
  attrs: [string, string][] | null;
  attrGet: (name: string) => string | null;
}

/**
 * 将 Markdown 内容导出为 DOCX 文件
 * 支持图片嵌入（需要图片 URL 可访问）
 *
 * @param markdown - Markdown 内容
 * @param filename - 导出的文件名（不含扩展名）
 * @param accessToken - 可选的访问令牌，用于图片 URL
 */
export async function exportMarkdownToDocx(
  markdown: string,
  filename: string = "document",
  accessToken?: string,
): Promise<void> {
  // 解析 Markdown 为 tokens
  const md = new MarkdownIt({
    html: true,
    linkify: true,
    typographer: true,
  });

  const tokens = md.parse(markdown, {}) as MdToken[];
  void findImagesInTokens(tokens);

  // 转换 tokens 为 docx 元素
  const children = await tokensToDocxElements(tokens, accessToken);

  // 创建文档
  const doc = new Document({
    sections: [
      {
        properties: {},
        children: children,
      },
    ],
  });

  // 生成并保存文件
  const blob = await Packer.toBlob(doc);
  saveAs(blob, `${filename}.docx`);
}

/**
 * 递归查找 tokens 中的图片
 */
function findImagesInTokens(tokens: MdToken[]): string[] {
  const images: string[] = [];

  for (const token of tokens) {
    if (token.type === "image") {
      const src = token.attrGet?.("src") || "";
      if (src) images.push(src);
    }
    if (token.children) {
      images.push(...findImagesInTokens(token.children));
    }
  }

  return images;
}

/**
 * 将 markdown-it tokens 转换为 docx 元素
 */
async function tokensToDocxElements(
  tokens: MdToken[],
  accessToken?: string,
): Promise<(Paragraph | Table)[]> {
  const elements: (Paragraph | Table)[] = [];
  let i = 0;

  while (i < tokens.length) {
    const tok = tokens[i];

    if (tok.type === "heading_open") {
      const level = parseInt(tok.tag.slice(1)) as 1 | 2 | 3 | 4 | 5 | 6;
      const contentToken = tokens[i + 1];
      const text = contentToken?.content || "";

      elements.push(
        new Paragraph({
          text: text,
          heading: getHeadingLevel(level),
          spacing: { before: 240, after: 120 },
        }),
      );
      i += 3; // skip heading_open, inline, heading_close
    } else if (tok.type === "paragraph_open") {
      const contentToken = tokens[i + 1];
      if (contentToken) {
        const runs = await inlineTokenToRuns(contentToken, accessToken);
        elements.push(
          new Paragraph({
            children: runs,
            spacing: { after: 120 },
          }),
        );
      }
      i += 3; // skip paragraph_open, inline, paragraph_close
    } else if (
      tok.type === "bullet_list_open" ||
      tok.type === "ordered_list_open"
    ) {
      const isOrdered = tok.type === "ordered_list_open";
      const listElements = await parseList(tokens, i, isOrdered, accessToken);
      elements.push(...listElements.elements);
      i = listElements.endIndex + 1;
    } else if (tok.type === "fence" || tok.type === "code_block") {
      // 代码块
      const codeContent = tok.content || "";
      const lines = codeContent.split("\n");

      for (const line of lines) {
        elements.push(
          new Paragraph({
            children: [
              new TextRun({
                text: line || " ",
                font: "Consolas",
                size: 20, // 10pt
              }),
            ],
            shading: {
              fill: "F5F5F5",
            },
            spacing: { after: 0 },
          }),
        );
      }
      elements.push(new Paragraph({ text: "" })); // 空行
      i++;
    } else if (tok.type === "blockquote_open") {
      const quoteElements = await parseBlockquote(tokens, i, accessToken);
      elements.push(...quoteElements.elements);
      i = quoteElements.endIndex + 1;
    } else if (tok.type === "table_open") {
      const tableResult = await parseTable(tokens, i, accessToken);
      elements.push(tableResult.table);
      i = tableResult.endIndex + 1;
    } else if (tok.type === "hr") {
      elements.push(
        new Paragraph({
          children: [new TextRun({ text: "─".repeat(50) })],
          alignment: AlignmentType.CENTER,
        }),
      );
      i++;
    } else {
      i++;
    }
  }

  return elements;
}

/**
 * 解析列表
 */
async function parseList(
  tokens: MdToken[],
  startIndex: number,
  isOrdered: boolean,
  accessToken?: string,
): Promise<{ elements: Paragraph[]; endIndex: number }> {
  const elements: Paragraph[] = [];
  let i = startIndex + 1;
  let itemNumber = 1;

  while (i < tokens.length) {
    const tok = tokens[i];

    if (tok.type === "list_item_open") {
      i++;
    } else if (tok.type === "list_item_close") {
      itemNumber++;
      i++;
    } else if (tok.type === "paragraph_open") {
      const contentToken = tokens[i + 1];
      if (contentToken) {
        const runs = await inlineTokenToRuns(contentToken, accessToken);
        const bullet = isOrdered ? `${itemNumber}. ` : "• ";
        elements.push(
          new Paragraph({
            children: [new TextRun({ text: bullet }), ...runs],
            indent: { left: 720 }, // 0.5 inch
            spacing: { after: 60 },
          }),
        );
      }
      i += 3;
    } else if (
      tok.type === "bullet_list_open" ||
      tok.type === "ordered_list_open"
    ) {
      // 嵌套列表
      const nestedResult = await parseList(
        tokens,
        i,
        tok.type === "ordered_list_open",
        accessToken,
      );
      elements.push(...nestedResult.elements);
      i = nestedResult.endIndex + 1;
    } else if (
      tok.type === "bullet_list_close" ||
      tok.type === "ordered_list_close"
    ) {
      return { elements, endIndex: i };
    } else {
      i++;
    }
  }

  return { elements, endIndex: i };
}

/**
 * 解析引用块
 */
async function parseBlockquote(
  tokens: MdToken[],
  startIndex: number,
  accessToken?: string,
): Promise<{ elements: Paragraph[]; endIndex: number }> {
  const elements: Paragraph[] = [];
  let i = startIndex + 1;

  while (i < tokens.length) {
    const tok = tokens[i];

    if (tok.type === "blockquote_close") {
      return { elements, endIndex: i };
    } else if (tok.type === "paragraph_open") {
      const contentToken = tokens[i + 1];
      if (contentToken) {
        const runs = await inlineTokenToRuns(contentToken, accessToken);
        elements.push(
          new Paragraph({
            children: runs,
            indent: { left: 720 },
            border: {
              left: {
                color: "CCCCCC",
                size: 24,
                style: BorderStyle.SINGLE,
              },
            },
            spacing: { after: 60 },
          }),
        );
      }
      i += 3;
    } else {
      i++;
    }
  }

  return { elements, endIndex: i };
}

/**
 * 解析表格
 */
async function parseTable(
  tokens: MdToken[],
  startIndex: number,
  accessToken?: string,
): Promise<{ table: Table; endIndex: number }> {
  const rows: TableRow[] = [];
  let i = startIndex + 1;
  let isHeader = false;

  while (i < tokens.length) {
    const tok = tokens[i];

    if (tok.type === "table_close") {
      break;
    } else if (tok.type === "thead_open") {
      isHeader = true;
      i++;
    } else if (tok.type === "thead_close") {
      isHeader = false;
      i++;
    } else if (tok.type === "tbody_open" || tok.type === "tbody_close") {
      i++;
    } else if (tok.type === "tr_open") {
      const rowResult = await parseTableRow(tokens, i, isHeader, accessToken);
      rows.push(rowResult.row);
      i = rowResult.endIndex + 1;
    } else {
      i++;
    }
  }

  return {
    table: new Table({
      rows: rows,
      width: { size: 100, type: WidthType.PERCENTAGE },
    }),
    endIndex: i,
  };
}

/**
 * 解析表格行
 */
async function parseTableRow(
  tokens: MdToken[],
  startIndex: number,
  isHeader: boolean,
  accessToken?: string,
): Promise<{ row: TableRow; endIndex: number }> {
  const cells: TableCell[] = [];
  let i = startIndex + 1;

  while (i < tokens.length) {
    const tok = tokens[i];

    if (tok.type === "tr_close") {
      break;
    } else if (tok.type === "th_open" || tok.type === "td_open") {
      const contentToken = tokens[i + 1];
      let runs: (TextRun | ImageRun | ExternalHyperlink)[] = [];
      if (contentToken && contentToken.type === "inline") {
        runs = await inlineTokenToRuns(contentToken, accessToken);
      }

      cells.push(
        new TableCell({
          children: [new Paragraph({ children: runs })],
          shading: isHeader ? { fill: "F5F5F5" } : undefined,
        }),
      );
      i += 3; // skip open, inline, close
    } else {
      i++;
    }
  }

  return {
    row: new TableRow({ children: cells }),
    endIndex: i,
  };
}

/**
 * 将 inline token 转换为 TextRun 数组
 */
async function inlineTokenToRuns(
  token: MdToken,
  accessToken?: string,
): Promise<(TextRun | ImageRun | ExternalHyperlink)[]> {
  const runs: (TextRun | ImageRun | ExternalHyperlink)[] = [];

  if (!token.children || token.children.length === 0) {
    if (token.content) {
      runs.push(new TextRun({ text: token.content }));
    }
    return runs;
  }

  let i = 0;
  let bold = false;
  let italic = false;
  let strikethrough = false;

  while (i < token.children.length) {
    const child = token.children[i];

    if (child.type === "text") {
      runs.push(
        new TextRun({
          text: child.content,
          bold: bold,
          italics: italic,
          strike: strikethrough,
        }),
      );
    } else if (child.type === "code_inline") {
      runs.push(
        new TextRun({
          text: child.content,
          font: "Consolas",
          size: 20,
          shading: { fill: "F5F5F5" },
        }),
      );
    } else if (child.type === "strong_open") {
      bold = true;
    } else if (child.type === "strong_close") {
      bold = false;
    } else if (child.type === "em_open") {
      italic = true;
    } else if (child.type === "em_close") {
      italic = false;
    } else if (child.type === "s_open") {
      strikethrough = true;
    } else if (child.type === "s_close") {
      strikethrough = false;
    } else if (child.type === "link_open") {
      const href = child.attrGet?.("href") || "";
      const textToken = token.children[i + 1];
      const linkText = textToken?.content || href;

      runs.push(
        new ExternalHyperlink({
          children: [
            new TextRun({
              text: linkText,
              color: "0066CC",
              underline: {},
            }),
          ],
          link: href,
        }),
      );
      i += 2; // skip text and link_close
    } else if (child.type === "image") {
      const src = child.attrGet?.("src") || "";
      const alt = child.attrGet?.("alt") || child.content || "image";

      try {
        const imageData = await fetchImageAsBuffer(src, accessToken);
        if (imageData) {
          runs.push(
            new ImageRun({
              data: imageData.buffer,
              transformation: {
                width: Math.min(imageData.width, 500),
                height: Math.min(imageData.height, 400),
              },
              type: imageData.type as "png" | "jpg" | "gif" | "bmp",
            }),
          );
        } else {
          // 图片加载失败，显示 alt 文本
          runs.push(
            new TextRun({
              text: `[图片: ${alt}]`,
              italics: true,
              color: "666666",
            }),
          );
        }
      } catch {
        runs.push(
          new TextRun({
            text: `[图片: ${alt}]`,
            italics: true,
            color: "666666",
          }),
        );
      }
    } else if (child.type === "softbreak" || child.type === "hardbreak") {
      runs.push(new TextRun({ text: "", break: 1 }));
    }

    i++;
  }

  return runs;
}

/**
 * 获取图片数据
 */
async function fetchImageAsBuffer(
  url: string,
  accessToken?: string,
): Promise<{
  buffer: ArrayBuffer;
  width: number;
  height: number;
  type: string;
} | null> {
  try {
    let finalUrl = url;

    // ...

    // 将绝对路径转换为相对路径
    finalUrl = stripApiBaseUrl(finalUrl);

    if (finalUrl.includes("/api/")) {
      const apiIndex = finalUrl.indexOf("/api/");
      finalUrl = finalUrl.substring(apiIndex);
    }

    // 如果是相对路径，不需要加 origin（让 Vite 代理处理）
    // 如果是非 API 的绝对路径，保持原样

    // 添加访问令牌
    if (accessToken && finalUrl.includes("/api/")) {
      const separator = finalUrl.includes("?") ? "&" : "?";
      finalUrl = `${finalUrl}${separator}access_token=${accessToken}`;
    }

    const response = await apiFetch(finalUrl);

    if (!response.ok) {
      throw new Error(`Failed to fetch image: ${response.status}`);
    }

    const blob = await response.blob();
    const buffer = await blob.arrayBuffer();

    // 获取图片尺寸
    const dimensions = await getImageDimensions(blob);

    // 确定图片类型
    let type = "png";
    if (blob.type.includes("jpeg") || blob.type.includes("jpg")) {
      type = "jpg";
    } else if (blob.type.includes("gif")) {
      type = "gif";
    } else if (blob.type.includes("bmp")) {
      type = "bmp";
    }

    return {
      buffer,
      width: dimensions.width,
      height: dimensions.height,
      type,
    };
  } catch {
    return null;
  }
}

/**
 * 获取图片尺寸
 */
function getImageDimensions(
  blob: Blob,
): Promise<{ width: number; height: number }> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      resolve({ width: img.width, height: img.height });
      URL.revokeObjectURL(img.src);
    };
    img.onerror = () => {
      resolve({ width: 400, height: 300 }); // 默认尺寸
      URL.revokeObjectURL(img.src);
    };
    img.src = URL.createObjectURL(blob);
  });
}

/**
 * 获取标题级别
 */
function getHeadingLevel(
  level: number,
): (typeof HeadingLevel)[keyof typeof HeadingLevel] {
  switch (level) {
    case 1:
      return HeadingLevel.HEADING_1;
    case 2:
      return HeadingLevel.HEADING_2;
    case 3:
      return HeadingLevel.HEADING_3;
    case 4:
      return HeadingLevel.HEADING_4;
    case 5:
      return HeadingLevel.HEADING_5;
    case 6:
      return HeadingLevel.HEADING_6;
    default:
      return HeadingLevel.HEADING_1;
  }
}
