import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { DatabaseConnector } from "@/types/databaseConnectors";
import type { ConnectorFormState } from "./types";

interface ConnectionFieldsProps {
  form: ConnectorFormState;
  connector?: DatabaseConnector | null;
  onFormChange: (updates: Partial<ConnectorFormState>) => void;
}

export function ConnectionFields({
  form,
  connector,
  onFormChange,
}: ConnectionFieldsProps) {
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="connector-host">主机</Label>
          <Input
            id="connector-host"
            value={form.host}
            onChange={(event) => onFormChange({ host: event.target.value })}
            placeholder="127.0.0.1"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="connector-port">端口</Label>
          <Input
            id="connector-port"
            type="number"
            value={form.port}
            onChange={(event) => onFormChange({ port: event.target.value })}
            placeholder={
              form.db_type === "mysql"
                ? "3306"
                : form.db_type === "influxdb3"
                  ? "8181"
                  : "5432"
            }
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="connector-database-name">数据库名</Label>
          <Input
            id="connector-database-name"
            value={form.database_name}
            onChange={(event) =>
              onFormChange({ database_name: event.target.value })
            }
            placeholder="analytics"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="connector-username">目标数据库账号</Label>
          <Input
            id="connector-username"
            value={form.username}
            onChange={(event) =>
              onFormChange({ username: event.target.value })
            }
            placeholder="analytics_reader"
          />
          <p className="text-xs text-muted-foreground">
            填目标数据库里已经存在的账号，不是平台内的新账号。
          </p>
        </div>

        <div className="space-y-2 md:col-span-2">
          <Label htmlFor="connector-password">
            账号密码
            {connector?.has_password ? "（留空表示沿用已保存密码）" : ""}
          </Label>
          <Input
            id="connector-password"
            type="password"
            value={form.password}
            onChange={(event) =>
              onFormChange({ password: event.target.value })
            }
            placeholder={connector?.password_masked ?? "输入目标数据库账号密码"}
          />
        </div>
      </div>

      <Collapsible open={isAdvancedOpen} onOpenChange={setIsAdvancedOpen}>
        <div className="rounded-lg border border-border bg-muted/15">
          <div className="flex items-start justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <div className="text-sm font-medium text-foreground">高级选项</div>
              <div className="mt-1 text-xs leading-5 text-muted-foreground">
                默认无需调整，需要暴露原始凭据时再展开。
              </div>
            </div>
            <CollapsibleTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="gap-1.5 px-2 text-muted-foreground"
              >
                <ChevronDown
                  className={cn(
                    "h-4 w-4 transition-transform",
                    isAdvancedOpen && "rotate-180",
                  )}
                />
                {isAdvancedOpen ? "收起" : "展开"}
              </Button>
            </CollapsibleTrigger>
          </div>
          <CollapsibleContent>
            <div className="border-t border-border px-4 py-4">
              <div className="flex items-center justify-between space-y-0 gap-4 rounded-lg border border-border bg-background px-4 py-4">
                <div className="space-y-0.5">
                  <Label
                    htmlFor="connector-allow-notebook"
                    className="text-base"
                  >
                    导出凭据给 Notebook 运行时
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    默认关闭。开启后，当前会话挂载此连接时，后端会把账号密码写入本机会话凭据文件，Notebook 代码可以用 Python 驱动直连目标数据库。
                  </p>
                  <p className="text-xs text-muted-foreground">
                    只在 Notebook 里需要手写数据库连接代码时开启；数据查询面板和 Agent 查询不需要它。
                  </p>
                </div>
                <Switch
                  id="connector-allow-notebook"
                  checked={form.allow_notebook_access}
                  onCheckedChange={(checked) =>
                    onFormChange({ allow_notebook_access: checked })
                  }
                />
              </div>
            </div>
          </CollapsibleContent>
        </div>
      </Collapsible>
    </div>
  );
}
