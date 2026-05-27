import React from "react";
import { FileImage, FilePlus2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { isImageFile } from "@/utils/fileTreeUtils";
import { getWorkspaceFileLabel } from "./canvasUtils";
import type { WorkspaceFile } from "@/types/task";
import type { FilePickerMode } from "./useCanvasHandlers";

interface EdgeLabelDialogProps {
  open: boolean;
  value: string;
  onValueChange: (value: string) => void;
  onCommit: () => void;
  onCancel: () => void;
}

export const EdgeLabelDialog: React.FC<EdgeLabelDialogProps> = ({
  open,
  value,
  onValueChange,
  onCommit,
  onCancel,
}) => {
  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) onCancel(); }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>编辑连线标签</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            value={value}
            autoFocus
            placeholder="输入标签，可留空"
            onChange={(event) => onValueChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                onCommit();
              }
            }}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={onCancel}>
              取消
            </Button>
            <Button size="sm" onClick={onCommit}>
              保存
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

interface FilePickerDialogProps {
  open: boolean;
  mode: FilePickerMode | null;
  query: string;
  candidates: WorkspaceFile[];
  onQueryChange: (value: string) => void;
  onSelectFile: (fileName: string, mode: FilePickerMode) => void;
  onClose: () => void;
}

export const FilePickerDialog: React.FC<FilePickerDialogProps> = ({
  open,
  mode,
  query,
  candidates,
  onQueryChange,
  onSelectFile,
  onClose,
}) => {
  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) onClose(); }}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {mode === "image" ? "添加图片节点" : "添加文档节点"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="搜索工作区文件..."
          />
          <div className="max-h-[360px] overflow-y-auto rounded-lg border border-border">
            {candidates.length > 0 ? (
              candidates.map((file) => {
                const Icon = isImageFile(file.name)
                  ? FileImage
                  : FilePlus2;
                return (
                  <button
                    key={file.name}
                    type="button"
                    className="flex w-full items-center gap-2 border-b border-border px-3 py-2 text-left text-sm last:border-b-0 hover:bg-muted"
                    onClick={() =>
                      mode && onSelectFile(file.name, mode)
                    }
                  >
                    <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-foreground">
                        {getWorkspaceFileLabel(file.name)}
                      </span>
                      <span className="block truncate text-[11px] text-muted-foreground">
                        {file.name}
                      </span>
                    </span>
                  </button>
                );
              })
            ) : (
              <div className="px-4 py-8 text-center text-sm text-muted-foreground">
                {mode === "image"
                  ? "当前工作区没有可用图片。"
                  : "当前工作区没有可用文档文件。"}
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
