/**
 * 远程模型获取对话框
 */

import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, AlertCircle } from "lucide-react";
import type { LLMModelConfigWithMeta, RemoteModelInfo } from "@/lib/api/llm";

interface FetchModelsDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  providerId: string;
  remoteModels: RemoteModelInfo[];
  selectedModels: Set<string>;
  models: LLMModelConfigWithMeta[];
  fetching: boolean;
  error: string;
  unsupported: boolean;
  manualModelName: string;
  batchCreating: boolean;
  onManualModelNameChange: (value: string) => void;
  onToggleModel: (modelName: string) => void;
  onSelectAll: (allNew: string[]) => void;
  onBatchAdd: () => void;
  onManualAdd: () => void;
}

export function FetchModelsDialog({
  isOpen,
  onOpenChange,
  providerId,
  remoteModels,
  selectedModels,
  models,
  fetching,
  error,
  unsupported,
  manualModelName,
  batchCreating,
  onManualModelNameChange,
  onToggleModel,
  onSelectAll,
  onBatchAdd,
  onManualAdd,
}: FetchModelsDialogProps) {
  const existingModelNames = useMemo(() => 
    new Set(models.filter((m) => m.provider === providerId).map((m) => m.model)),
    [models, providerId]
  );

  const allNewModels = useMemo(() => 
    remoteModels.map((m) => m.model_name).filter((name) => !existingModelNames.has(name)),
    [remoteModels, existingModelNames]
  );

  const handleSelectAll = () => {
    if (selectedModels.size === allNewModels.length) {
      onSelectAll([]);
    } else {
      onSelectAll(allNewModels);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>获取模型列表</DialogTitle>
          <DialogDescription>
            从服务商 API 获取可用模型，勾选后批量添加
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto py-4 space-y-4">
          {fetching && (
            <div className="flex justify-center py-8">
              <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
            </div>
          )}

          {/* 获取失败：显示错误 + 手动输入回退 */}
          {error && (
            <div className="space-y-4">
              <Alert variant={unsupported ? "default" : "destructive"}>
                <AlertCircle className="w-4 h-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
              <div className="space-y-2">
                <Label>手动输入模型名称</Label>
                <div className="flex gap-2">
                  <Input
                    value={manualModelName}
                    onChange={(e) => onManualModelNameChange(e.target.value)}
                    placeholder="例如: deepseek-v3"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        void onManualAdd();
                      }
                    }}
                  />
                  <Button
                    onClick={onManualAdd}
                    disabled={!manualModelName.trim() || batchCreating}
                  >
                    {batchCreating ? <Loader2 className="w-4 h-4 animate-spin" /> : "添加"}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* 模型列表 */}
          {!fetching && remoteModels.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">
                  共 {remoteModels.length} 个模型
                </span>
                <Button variant="ghost" size="sm" onClick={handleSelectAll}>
                  全选/取消全选
                </Button>
              </div>
              <div className="space-y-1 max-h-[40vh] overflow-y-auto border rounded-md p-2">
                {remoteModels.map((rm) => {
                  const isExisting = existingModelNames.has(rm.model_name);
                  return (
                    <div
                      key={rm.model_name}
                      className={`flex items-center space-x-3 py-2 px-2 rounded hover:bg-muted/50 ${
                        isExisting ? "opacity-60" : ""
                      }`}
                    >
                      <Checkbox
                        id={`rm-${rm.model_name}`}
                        checked={isExisting || selectedModels.has(rm.model_name)}
                        disabled={isExisting}
                        onCheckedChange={() => onToggleModel(rm.model_name)}
                      />
                      <Label
                        htmlFor={`rm-${rm.model_name}`}
                        className="flex-1 text-sm font-normal cursor-pointer flex flex-col gap-0.5"
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-mono">{rm.model_name}</span>
                          {rm.display_name && (
                            <span className="text-xs text-muted-foreground">{rm.display_name}</span>
                          )}
                          {rm.owned_by && (
                            <span className="text-xs text-muted-foreground">({rm.owned_by})</span>
                          )}
                          {isExisting && (
                            <Badge variant="secondary" className="text-[10px]">已添加</Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5">
                          {rm.context_length !== undefined && (
                            <Badge variant="outline" className="text-[10px] px-1 py-0 h-4">
                              {rm.context_length >= 1000
                                ? `${(rm.context_length / 1000).toFixed(0)}K 上下文`
                                : `${rm.context_length} 上下文`}
                            </Badge>
                          )}
                          {rm.supports_reasoning && (
                            <Badge variant="outline" className="text-[10px] px-1 py-0 h-4 text-info border-info/20">
                              reasoning
                            </Badge>
                          )}
                          {rm.supports_image_in && (
                            <Badge variant="outline" className="text-[10px] px-1 py-0 h-4 text-tertiary border-info/20">
                              图片
                            </Badge>
                          )}
                          {rm.supports_video_in && (
                            <Badge variant="outline" className="text-[10px] px-1 py-0 h-4 text-success border-success/20">
                              视频
                            </Badge>
                          )}
                          {rm.context_length === undefined && (
                            <span className="text-[10px] text-warning">未返回上下文长度，将使用默认值</span>
                          )}
                        </div>
                      </Label>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {!fetching && !error && remoteModels.length === 0 && !unsupported && (
            <p className="text-sm text-muted-foreground text-center py-4">
              未获取到模型列表
            </p>
          )}
        </div>

        {!unsupported && (
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button
              onClick={onBatchAdd}
              disabled={selectedModels.size === 0 || batchCreating}
            >
              {batchCreating && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              添加 {selectedModels.size > 0 ? `(${selectedModels.size})` : ""}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
