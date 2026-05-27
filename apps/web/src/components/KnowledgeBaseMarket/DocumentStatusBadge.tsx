import { Badge } from "@/components/ui/badge";
import { CheckCircle2, Loader2, XCircle, Clock } from "lucide-react";

interface DocumentStatusBadgeProps {
  status: string;
}

export function DocumentStatusBadge({ status }: DocumentStatusBadgeProps) {
  switch (status) {
    case "completed":
      return (
        <Badge variant="default" className="bg-success hover:bg-success">
          <CheckCircle2 className="w-3 h-3 mr-1" />
          已完成
        </Badge>
      );
    case "processing":
      return (
        <Badge variant="outline" className="text-tertiary border-tertiary">
          <Loader2 className="w-3 h-3 mr-1 animate-spin" />
          处理中
        </Badge>
      );
    case "failed":
      return (
        <Badge
          variant="default"
          className="bg-destructive text-destructive-foreground"
        >
          <XCircle className="w-3 h-3 mr-1" />
          失败
        </Badge>
      );
    case "pending":
    default:
      return (
        <Badge variant="secondary">
          <Clock className="w-3 h-3 mr-1" />
          待处理
        </Badge>
      );
  }
}
