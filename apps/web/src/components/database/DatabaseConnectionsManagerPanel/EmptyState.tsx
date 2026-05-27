import { Database, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  onCreate: () => void;
}

export function EmptyState({ onCreate }: EmptyStateProps) {
  return (
    <div className="rounded-lg border border-dashed border-border px-4 py-12 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-border">
        <Database className="h-5 w-5 text-muted-foreground" />
      </div>
      <p className="mt-4 text-sm font-medium text-foreground">还没有数据库连接</p>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        创建 PostgreSQL、MySQL 或 InfluxDB 3 连接，按账号密码接入即可。平台仅开放只读查询，写入权限由目标数据库账号自身控制。
      </p>
      <div className="mt-4">
        <Button onClick={onCreate}>
          <Plus className="h-4 w-4" />
          新建第一个连接
        </Button>
      </div>
    </div>
  );
}
