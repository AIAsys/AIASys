/**
 * CheckpointReviewDialog - 检查点评审对话框
 *
 * 将 CheckpointReview 组件包装为对话框形式，用于 AskUser 流程中的检查点评审
 */

import { useState } from 'react';
import type { CheckpointReviewData, AskUserValue } from '@/types/askUser';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  CheckCircle2,
  XCircle,
  FileText,
  Clock,
  AlertTriangle,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface CheckpointReviewDialogProps {
  checkpointData: CheckpointReviewData;
  isOpen: boolean;
  isLoading?: boolean;
  errorMessage?: string | null;
  onResponse: (approved: boolean, value?: AskUserValue) => Promise<boolean>;
  onClose: () => void;
}

export function CheckpointReviewDialog({
  checkpointData,
  isOpen,
  isLoading = false,
  errorMessage,
  onResponse,
  onClose,
}: CheckpointReviewDialogProps) {
  const [comments, setComments] = useState('');
  const [showReworkInput, setShowReworkInput] = useState(false);
  const [reworkTasks, setReworkTasks] = useState<string[]>(['']);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const passedCount = checkpointData.deliverables.filter((d) => d.status === 'PASS').length;
  const totalCount = checkpointData.deliverables.length;
  const allPassed = passedCount === totalCount && checkpointData.auto_check_passed;

  const handleAddReworkTask = () => {
    setReworkTasks([...reworkTasks, '']);
  };

  const handleUpdateReworkTask = (index: number, value: string) => {
    const newTasks = [...reworkTasks];
    newTasks[index] = value;
    setReworkTasks(newTasks);
  };

  const handleRemoveReworkTask = (index: number) => {
    const newTasks = reworkTasks.filter((_, i) => i !== index);
    setReworkTasks(newTasks);
  };

  const handleApprove = async () => {
    if (isSubmitting || isLoading) return;

    setIsSubmitting(true);
    try {
      const value: AskUserValue = {
        action: 'approve',
        comments: comments.trim() || undefined,
        checkpoint_id: checkpointData.checkpoint_id,
      };
      const success = await onResponse(true, value);
      if (success) {
        onClose();
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (isSubmitting || isLoading) return;

    const validTasks = reworkTasks.filter((t) => t.trim());
    if (validTasks.length === 0) return;

    setIsSubmitting(true);
    try {
      const value: AskUserValue = {
        action: 'reject',
        comments: comments.trim() || undefined,
        rework_tasks: validTasks,
        checkpoint_id: checkpointData.checkpoint_id,
      };
      const success = await onResponse(false, value);
      if (success) {
        onClose();
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center space-x-2 mb-1">
                <Badge variant="outline" className="text-xs">
                  {checkpointData.checkpoint_id}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {checkpointData.phase_name}
                </span>
              </div>
              <DialogTitle className="text-xl">{checkpointData.title}</DialogTitle>
              <p className="text-muted-foreground mt-1">{checkpointData.description}</p>
            </div>
            <div className="p-3 rounded-full bg-warning-container">
              <Clock className="w-6 h-6 text-warning" />
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* 错误信息 */}
          {errorMessage && (
            <div className="p-4 rounded-lg border border-error/20 bg-error-container text-error">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" />
                <span className="font-medium">提交失败</span>
              </div>
              <p className="text-sm mt-1">{errorMessage}</p>
            </div>
          )}

          {/* 交付物检查 */}
          <div className="space-y-3">
            <h3 className="font-semibold flex items-center">
              <FileText className="w-4 h-4 mr-2" />
              交付物检查 ({passedCount}/{totalCount})
            </h3>
            <div className="space-y-2">
              {checkpointData.deliverables.map((item, index) => (
                <div
                  key={`${item.item}-${index}`}
                  className={cn(
                    'flex items-center justify-between p-3 rounded-lg border',
                    item.status === 'PASS'
                      ? 'bg-success-container border-success/20'
                      : item.status === 'FAIL'
                        ? 'bg-error-container border-error/20'
                        : 'bg-muted border-border'
                  )}
                >
                  <div className="flex items-center space-x-3">
                    {item.status === 'PASS' ? (
                      <CheckCircle2 className="w-5 h-5 text-success" />
                    ) : item.status === 'FAIL' ? (
                      <XCircle className="w-5 h-5 text-error" />
                    ) : (
                      <Clock className="w-5 h-5 text-muted-foreground" />
                    )}
                    <div>
                      <span
                        className={cn(
                          'font-medium',
                          item.status === 'PASS'
                            ? 'text-success'
                            : item.status === 'FAIL'
                              ? 'text-error'
                              : 'text-muted-foreground'
                        )}
                      >
                        {item.item}
                      </span>
                      {item.path && (
                        <p className="text-xs text-muted-foreground">{item.path}</p>
                      )}
                    </div>
                  </div>
                  <Badge
                    variant="secondary"
                    className={cn(
                      item.status === 'PASS'
                        ? 'bg-success-container text-success'
                        : item.status === 'FAIL'
                          ? 'bg-error-container text-error'
                          : 'bg-muted text-muted-foreground'
                    )}
                  >
                    {item.status === 'PASS'
                      ? '通过'
                      : item.status === 'FAIL'
                        ? '缺失'
                        : '待检查'}
                  </Badge>
                </div>
              ))}
            </div>
          </div>

          {/* 自定义检查项 */}
          {checkpointData.custom_checks.length > 0 && (
            <div className="space-y-3">
              <h3 className="font-semibold">自动检查项</h3>
              <div className="space-y-2">
                {checkpointData.custom_checks.map((check, index) => (
                  <div
                    key={`${check.item}-${index}`}
                    className="flex items-center justify-between p-2 rounded-md bg-muted"
                  >
                    <span className="text-sm text-muted-foreground">{check.item}</span>
                    <div className="flex items-center space-x-2">
                      {check.note && (
                        <span className="text-xs text-muted-foreground">{check.note}</span>
                      )}
                      <Badge
                        variant="outline"
                        className={cn(
                          'text-xs',
                          check.status === 'PASS'
                            ? 'border-success/20 text-success'
                            : check.status === 'FAIL'
                              ? 'border-error/20 text-error'
                              : 'border-border text-muted-foreground'
                        )}
                      >
                        {check.status}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 审批意见 */}
          <div className="space-y-3">
            <label className="text-sm font-medium">审批意见</label>
            <Textarea
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="请输入审批意见（可选）..."
              className="min-h-[80px]"
            />
          </div>

          {/* 整改任务输入 */}
          {showReworkInput && (
            <div className="space-y-3 p-4 rounded-lg border border-warning/20 bg-warning-container">
              <h3 className="font-semibold text-warning flex items-center">
                <AlertTriangle className="w-4 h-4 mr-2" />
                整改任务
              </h3>
              <div className="space-y-2">
                {reworkTasks.map((task, index) => (
                  <div key={`rework-${task.slice(0, 16)}-${index}`} className="flex items-center space-x-2">
                    <Textarea
                      value={task}
                      onChange={(e) => handleUpdateReworkTask(index, e.target.value)}
                      placeholder={`整改任务 ${index + 1}...`}
                      className="flex-1 min-h-[60px]"
                    />
                    {reworkTasks.length > 1 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveReworkTask(index)}
                        className="text-error shrink-0"
                      >
                        删除
                      </Button>
                    )}
                  </div>
                ))}
              </div>
              <Button variant="outline" size="sm" onClick={handleAddReworkTask} className="w-full">
                添加整改任务
              </Button>
            </div>
          )}
        </div>

        {/* 操作按钮 */}
        <div className="flex justify-end space-x-3 pt-4 border-t">
          {showReworkInput ? (
            <Button
              variant="destructive"
              onClick={handleReject}
              disabled={
                isSubmitting ||
                isLoading ||
                reworkTasks.filter((t) => t.trim()).length === 0
              }
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  提交中...
                </>
              ) : (
                <>
                  <XCircle className="w-4 h-4 mr-2" />
                  确认不通过
                </>
              )}
            </Button>
          ) : (
            <Button
              variant="outline"
              onClick={() => setShowReworkInput(true)}
              className="text-warning border-warning/20 hover:bg-warning-container"
              disabled={isSubmitting || isLoading}
            >
              <XCircle className="w-4 h-4 mr-2" />
              需要整改
            </Button>
          )}

          <Button
            onClick={handleApprove}
            className="bg-success hover:bg-success"
            disabled={isSubmitting || isLoading || !allPassed}
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                提交中...
              </>
            ) : (
              <>
                <CheckCircle2 className="w-4 h-4 mr-2" />
                通过
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
