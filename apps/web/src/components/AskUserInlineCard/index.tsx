/**
 * AskUser 内联卡片组件
 *
 * 在聊天流中以内联卡片形式展示 AskUser 请求，替代弹窗。
 * 支持 confirm / input / select / multi_select 类型。
 */

import React, { useState, useEffect, useCallback, useRef } from "react";
import type { AskUserRequest, AskUserValue } from "@/types/askUser";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { AlertCircle, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { formatMessage } from "@/utils/askUserMessageFormatter";

interface AskUserInlineCardProps {
  request: AskUserRequest;
  status: "pending" | "approved" | "rejected" | "timeout";
  onResponse: (approved: boolean, value?: AskUserValue) => Promise<boolean>;
}

function parseCreatedAt(createdAt?: string): number {
  if (!createdAt) return Date.now();
  const timestamp = new Date(createdAt).getTime();
  return Number.isNaN(timestamp) ? Date.now() : timestamp;
}

function getRemainingSeconds(request: AskUserRequest): number {
  const expiresAt = parseCreatedAt(request.created_at) + request.timeout * 1000;
  return Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
}

function formatRemainingTime(seconds: number): string {
  if (seconds <= 0) return "已超时";
  const minutes = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (minutes === 0) return `${s} 秒`;
  return `${minutes} 分 ${s.toString().padStart(2, "0")} 秒`;
}

export const AskUserInlineCard: React.FC<AskUserInlineCardProps> = ({
  request,
  status,
  onResponse,
}) => {
  const [inputValue, setInputValue] = useState("");
  const [selectedValue, setSelectedValue] = useState<string>("");
  const [selectedValues, setSelectedValues] = useState<string[]>([]);
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const timeoutCalledRef = useRef(false);
  const lastRequestIdRef = useRef<string>("");

  useEffect(() => {
    const requestIdChanged = lastRequestIdRef.current !== request.request_id;
    lastRequestIdRef.current = request.request_id;

    // 只在 request_id 真正变化时重置用户输入，避免后端推送相同 request 更新时丢失用户输入
    if (requestIdChanged) {
      setInputValue(
        request.type === "input" && typeof request.default_value === "string"
          ? request.default_value
          : "",
      );
      setSelectedValue(
        request.type === "select" && typeof request.default_value === "string"
          ? request.default_value
          : "",
      );
      setSelectedValues(
        request.type === "multi_select" && Array.isArray(request.default_value)
          ? request.default_value.filter((item): item is string => typeof item === "string")
          : [],
      );
      setErrorMessage(null);
      timeoutCalledRef.current = false;
    }

    // 每次 request 变化都更新倒计时（timeout 可能变化）
    setRemainingSeconds(getRemainingSeconds(request));
  }, [request]);

  useEffect(() => {
    if (status !== "pending") return;
    const timer = window.setInterval(() => {
      setRemainingSeconds(getRemainingSeconds(request));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [request, status]);

  // 超时后仅更新 UI，不再自动向后端发送拒绝响应。
  // 后端有自己的 asyncio.wait_for 超时机制；前端因时钟偏差/网络延迟
  // 自动发送拒绝会导致"还没操作就自动取消"的 bug。
  useEffect(() => {
    if (status !== "pending" || remainingSeconds > 0 || timeoutCalledRef.current) return;
    timeoutCalledRef.current = true;
    // 仅标记本地超时，不调用 onResponse(false)
  }, [status, remainingSeconds]);

  const isTimedOut = remainingSeconds <= 0;
  const isTerminal = status !== "pending";

  const handleConfirm = useCallback(async () => {
    if (isTerminal || isSubmitting) return;

    let value: AskUserValue | undefined;
    switch (request.type) {
      case "confirm":
        value = undefined;
        break;
      case "input":
        value = inputValue;
        break;
      case "select":
        value = selectedValue;
        break;
      case "multi_select":
        value = selectedValues;
        break;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const success = await onResponse(true, value);
      if (!success) {
        setErrorMessage("响应提交失败，请重试");
      }
    } catch (e) {
      setErrorMessage("提交异常，请重试");
    } finally {
      setIsSubmitting(false);
    }
  }, [isTerminal, isSubmitting, request.type, inputValue, selectedValue, selectedValues, onResponse]);

  const handleCancel = useCallback(async () => {
    if (isTerminal || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const success = await onResponse(false);
      if (!success) {
        setErrorMessage("响应提交失败，请重试");
      }
    } catch (e) {
      setErrorMessage("提交异常，请重试");
    } finally {
      setIsSubmitting(false);
    }
  }, [isTerminal, isSubmitting, onResponse]);

  const isConfirmDisabled = () => {
    if (isSubmitting || isTerminal) return true;
    switch (request.type) {
      case "input":
        return !inputValue.trim();
      case "select":
        return !selectedValue;
      case "multi_select":
        return selectedValues.length === 0;
      default:
        return false;
    }
  };

  const renderStatus = () => {
    if (status === "approved") {
      return (
        <div className="flex items-center gap-2 py-2">
          <CheckCircle2 className="h-4 w-4 text-green-600" />
          <span className="text-sm text-green-600">已确认</span>
        </div>
      );
    }
    if (status === "timeout" || isTimedOut) {
      return (
        <div className="flex items-center gap-2 py-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          请求已超时
        </div>
      );
    }
    if (status === "rejected") {
      return (
        <div className="flex items-center gap-2 py-2">
          <XCircle className="h-4 w-4 text-amber-600" />
          <span className="text-sm text-amber-600">已取消</span>
        </div>
      );
    }
    return (
      <div className={`text-xs ${remainingSeconds <= 30 ? "text-destructive" : "text-muted-foreground"}`}>
        剩余时间: {formatRemainingTime(remainingSeconds)}
      </div>
    );
  };

  const renderForm = () => {
    if (status !== "pending" || isTimedOut) {
      return (
        <div className="text-sm text-muted-foreground py-2">
          {formatMessage(request.message)}
        </div>
      );
    }

    switch (request.type) {
      case "confirm":
        return <div className="text-sm">{formatMessage(request.message)}</div>;

      case "input":
        return (
          <div className="space-y-3">
            <div className="text-sm">{formatMessage(request.message)}</div>
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={request.placeholder}
              className="w-full"
              autoFocus
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !isConfirmDisabled() &&
                  !e.nativeEvent.isComposing
                ) {
                  handleConfirm();
                }
              }}
            />
          </div>
        );

      case "select":
        return (
          <div className="space-y-3">
            <div className="text-sm">{formatMessage(request.message)}</div>
            <RadioGroup value={selectedValue} onValueChange={setSelectedValue} className="space-y-2">
              {request.options?.map((option) => (
                <div key={option.value} className="flex items-center space-x-2">
                  <RadioGroupItem value={option.value} id={`${request.request_id}-${option.value}`} />
                  <Label htmlFor={`${request.request_id}-${option.value}`} className="cursor-pointer text-sm">
                    {option.label}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          </div>
        );

      case "multi_select":
        return (
          <div className="space-y-3">
            <div className="text-sm">{formatMessage(request.message)}</div>
            <div className="space-y-2">
              {request.options?.map((option) => (
                <div key={option.value} className="flex items-center space-x-2">
                  <Checkbox
                    id={`${request.request_id}-${option.value}`}
                    checked={selectedValues.includes(option.value)}
                    onCheckedChange={(checked) => {
                      if (checked) {
                        setSelectedValues([...selectedValues, option.value]);
                      } else {
                        setSelectedValues(selectedValues.filter((v) => v !== option.value));
                      }
                    }}
                  />
                  <Label htmlFor={`${request.request_id}-${option.value}`} className="cursor-pointer text-sm">
                    {option.label}
                  </Label>
                </div>
              ))}
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card/60 p-4 space-y-3 my-2">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">{request.title}</h4>
        {renderStatus()}
      </div>

      {errorMessage && (
        <div className="flex items-center gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          {errorMessage}
        </div>
      )}

      {renderForm()}

      {status === "pending" && !isTimedOut && (
        <div className="flex justify-end gap-2 pt-1">
          <Button
            variant="outline"
            size="sm"
            onClick={handleCancel}
            disabled={isSubmitting}
          >
            {isSubmitting ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
            {request.type === "confirm" ? "取消" : "拒绝"}
          </Button>
          <Button
            size="sm"
            onClick={handleConfirm}
            disabled={isConfirmDisabled()}
          >
            {isSubmitting ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
            确认
          </Button>
        </div>
      )}
    </div>
  );
};
