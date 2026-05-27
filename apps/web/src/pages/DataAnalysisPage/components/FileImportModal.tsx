import { Check, FileText, Loader2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useFileImport } from "../hooks/useFileImport";

interface FileImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  targetSessionId: string;
  targetWorkspaceId?: string | null;
  onImportSuccess: () => void;
  apiBaseUrl?: string;
}

export function FileImportModal({
  isOpen,
  onClose,
  targetSessionId,
  targetWorkspaceId,
  onImportSuccess,
  apiBaseUrl,
}: FileImportModalProps) {
  const {
    sessions,
    sourceSessionFiles,
    isLoadingSessions,
    isLoadingSourceFiles,
    isImporting,
    error,
    setError,
    loadSessions,
    loadSourceSessionFiles,
    importFiles,
  } = useFileImport({
    baseUrl: apiBaseUrl,
    targetSessionId,
    targetWorkspaceId,
    onImportSuccess,
  });

  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [selectedFilenames, setSelectedFilenames] = useState<string[]>([]);
  const mounted = useRef(false);

  // 打开时加载历史对话列表
  useEffect(() => {
    if (isOpen && !mounted.current) {
      loadSessions();
      mounted.current = true;
    } else if (!isOpen) {
      mounted.current = false;
      setSelectedSessionId("");
      setSelectedFilenames([]);
      setError(null);
    }
  }, [isOpen, loadSessions, setError]);

  // 自动选择第一条非当前对话
  useEffect(() => {
    if (isOpen && sessions.length > 0 && !selectedSessionId) {
      const first = sessions.find((s) => s.session_id !== targetSessionId);
      if (first) {
        setSelectedSessionId(first.session_id);
      }
    }
  }, [isOpen, sessions, selectedSessionId, targetSessionId]);

  // 源对话改变时加载文件
  useEffect(() => {
    if (selectedSessionId) {
      loadSourceSessionFiles(selectedSessionId);
      setSelectedFilenames([]);
    }
  }, [selectedSessionId, loadSourceSessionFiles]);

  const handleToggleFile = (filename: string) => {
    setSelectedFilenames((prev) =>
      prev.includes(filename)
        ? prev.filter((f) => f !== filename)
        : [...prev, filename],
    );
  };

  const handleImport = async () => {
    try {
      await importFiles(selectedSessionId, selectedFilenames);
      onClose();
    } catch {
      // Error is handled in hook and displayed via error state
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-popover rounded-xl shadow-xl w-full max-w-lg overflow-hidden flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-lg font-semibold text-foreground">
            从历史对话导入文件
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-accent rounded-full text-muted-foreground transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Source Conversation Selector */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">
              选择源对话
            </label>
            <select
              value={selectedSessionId}
              onChange={(e) => setSelectedSessionId(e.target.value)}
              disabled={isLoadingSessions}
              className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring bg-background"
            >
              <option value="">
                {isLoadingSessions ? "加载中..." : "请选择对话..."}
              </option>
              {sessions
                .filter((s) => s.session_id !== targetSessionId)
                .filter((s) => Boolean(s.workspace_id))
                .map((s) => (
                  <option key={s.session_id} value={s.session_id}>
                    {s.session_id} ({s.file_count} 个文件) -{" "}
                    {new Date(s.updated_at * 1000).toLocaleDateString()}
                  </option>
                ))}
            </select>
          </div>

          {/* File List */}
          <div className="space-y-2 flex-1 min-h-[200px]">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-foreground">
                选择文件
              </label>
              {selectedFilenames.length > 0 && (
                <span className="text-xs text-foreground bg-muted px-2 py-0.5 rounded-full font-medium">
                  已选 {selectedFilenames.length} 个
                </span>
              )}
            </div>

            <div className="border border-border rounded-lg overflow-hidden h-64 overflow-y-auto bg-muted">
              {isLoadingSourceFiles ? (
                <div className="h-full flex items-center justify-center text-muted-foreground gap-2">
                  <Loader2 className="animate-spin w-5 h-5" />
                  加载文件列表...
                </div>
              ) : !selectedSessionId ? (
                <div className="h-full flex items-center justify-center text-muted-foreground">
                  请先选择一个对话
                </div>
              ) : sourceSessionFiles.length === 0 ? (
                <div className="h-full flex items-center justify-center text-muted-foreground">
                  该对话没有文件
                </div>
              ) : (
                <div className="divide-y divide-border bg-background">
                  {sourceSessionFiles.map((file) => (
                    <div
                      key={file.filename}
                      onClick={() => handleToggleFile(file.filename)}
                      className="flex items-center p-3 hover:bg-muted cursor-pointer transition-colors group"
                    >
                      <div
                        className={`w-5 h-5 rounded border mr-3 flex items-center justify-center transition-colors ${
                          selectedFilenames.includes(file.filename)
                            ? "bg-foreground border-foreground text-background"
                            : "border-border group-hover:border-muted-foreground"
                        }`}
                      >
                        {selectedFilenames.includes(file.filename) && (
                          <Check size={14} />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <FileText
                            size={16}
                            className="text-muted-foreground"
                          />
                          <span className="text-sm text-foreground truncate font-medium">
                            {file.filename}
                          </span>
                        </div>
                        <div className="text-xs text-muted-foreground ml-6 mt-0.5">
                          {(file.size / 1024).toFixed(1)} KB
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="p-3 bg-muted border border-border rounded-lg text-sm text-muted-foreground">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-muted border-t border-border flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
            disabled={isImporting}
          >
            取消
          </button>
          <button
            onClick={handleImport}
            disabled={isImporting || selectedFilenames.length === 0}
            className={`
                            px-4 py-2 text-sm font-medium text-white rounded-lg transition-all flex items-center gap-2
                            ${
                              isImporting || selectedFilenames.length === 0
                                ? "bg-muted text-muted-foreground cursor-not-allowed"
                                : "bg-foreground hover:bg-foreground/90 text-background shadow-sm hover:shadow"
                            }
                        `}
          >
            {isImporting && <Loader2 className="animate-spin w-4 h-4" />}
            {isImporting ? "导入中..." : "确认导入"}
          </button>
        </div>
      </div>
    </div>
  );
}
