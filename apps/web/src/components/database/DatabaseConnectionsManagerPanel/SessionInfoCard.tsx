import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface SessionInfoCardProps {
  sessionId?: string | null;
  attachmentsCount: number;
  onBackToSession?: (() => void) | null;
  compact?: boolean;
}

export function SessionInfoCard({
  sessionId,
  attachmentsCount,
  onBackToSession,
  compact,
}: SessionInfoCardProps) {
  if (!sessionId) {
    return null;
  }

  return (
    <Card>
      <CardHeader className={compact ? "p-3" : undefined}>
        <CardTitle className="text-base">当前会话</CardTitle>
        <CardDescription className={compact ? "text-xs leading-5" : undefined}>
          这里可以直接创建、编辑、测试，并把连接附加到当前会话或同步当前会话挂载策略。
        </CardDescription>
      </CardHeader>
      <CardContent
        className={compact ? "flex items-center justify-between gap-3 p-3" : "flex items-center justify-between gap-3"}
      >
        <div className={compact ? "text-xs text-muted-foreground" : "text-sm text-muted-foreground"}>
          当前会话已挂载 {attachmentsCount} 个数据库连接。
        </div>
        {onBackToSession ? (
          <Button variant="outline" size={compact ? "sm" : "default"} onClick={onBackToSession}>
            返回当前会话
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
