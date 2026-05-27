/**
 * FinalAnswerBlock - 最终回答块
 *
 * 显示 AI 的最终回答，支持导出为 Word
 */
import { memo, useMemo, useState, useCallback } from "react";
import { FileText, Loader2 } from "lucide-react";
import { useFileUploadToast } from "@/components/file/FileUploadToast";
import { useAiMessageContext } from "./context";
import { ChartAwareMarkdown } from "../ChartAwareMarkdown";

interface FinalAnswerBlockProps {
  content: string;
}

const normalizeMarkdown = (value?: string) =>
  String(value ?? "")
    .replace(/[\0]/g, "")
    .replace(/\r\n/g, "\n");

export const FinalAnswerBlock = memo(function FinalAnswerBlock({
  content,
}: FinalAnswerBlockProps) {
  const safeContent = useMemo(() => {
    const normalized = normalizeMarkdown(content);
    // 将 HTML <img> 标签转换为 Markdown 格式
    return normalized
      .replace(
        /<img[^>]+src=["']([^"']+)["'][^>]*alt=["']([^"]*)["'][^>]*\/?>/gi,
        "![$2]($1)",
      )
      .replace(
        /<img[^>]+alt=["']([^"]*)["'][^>]*src=["']([^"']+)["'][^>]*\/?>/gi,
        "![$1]($2)",
      );
  }, [content]);
  const {
    meta: { token, sessionId, onOpenWorkspaceArtifact },
  } = useAiMessageContext();
  const [isExporting, setIsExporting] = useState(false);
  const { showSuccess, showError } = useFileUploadToast();

  const handleExportDocx = useCallback(async () => {
    if (isExporting) return;
    setIsExporting(true);
    try {
      const timestamp = new Date().toISOString().slice(0, 10);
      const { exportMarkdownToDocx } = await import("@/utils/exportDocx");
      await exportMarkdownToDocx(safeContent, `AI回复_${timestamp}`, token);
      showSuccess("导出成功");
    } catch (error) {
      console.error("Failed to export DOCX:", error);
      showError("导出失败，请重试");
    } finally {
      setIsExporting(false);
    }
  }, [isExporting, safeContent, token, showSuccess, showError]);

  return (
    <div className="relative min-w-0">
      <div className="prose prose-sm max-w-none min-w-0 break-words px-4 py-2 text-sm leading-relaxed text-foreground [overflow-wrap:anywhere]">
        <ChartAwareMarkdown
          content={safeContent}
          token={token}
          sessionId={sessionId}
          onOpenInMainCanvas={onOpenWorkspaceArtifact}
        />
      </div>
      {/* 导出按钮 */}
      <div className="flex items-center gap-2 px-4 pt-2 pb-1">
        <button
          onClick={handleExportDocx}
          disabled={isExporting}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-muted hover:bg-accent border border-border text-muted-foreground hover:text-warning transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          title="导出为 Word 文档"
        >
          {isExporting ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <FileText size={14} />
          )}
          <span>{isExporting ? "导出中..." : "导出 Word"}</span>
        </button>
      </div>
    </div>
  );
});
