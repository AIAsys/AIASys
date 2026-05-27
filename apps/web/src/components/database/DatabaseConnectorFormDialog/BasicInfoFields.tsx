import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { DatabaseConnectorCapability, DatabaseType } from "@/types/databaseConnectors";
import type { ConnectorFormState } from "./types";

interface BasicInfoFieldsProps {
  form: ConnectorFormState;
  capabilities: DatabaseConnectorCapability[];
  onDbTypeChange: (type: DatabaseType) => void;
  onFormChange: (updates: Partial<ConnectorFormState>) => void;
}

export function BasicInfoFields({
  form,
  capabilities,
  onDbTypeChange,
  onFormChange,
}: BasicInfoFieldsProps) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="space-y-2">
        <Label htmlFor="connector-name">连接名称</Label>
        <Input
          id="connector-name"
          value={form.name}
          onChange={(event) => onFormChange({ name: event.target.value })}
          placeholder="例如：生产订单库"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="connector-db-type">数据库类型</Label>
        <Select
          value={form.db_type}
          onValueChange={(value) => onDbTypeChange(value as DatabaseType)}
        >
          <SelectTrigger id="connector-db-type">
            <SelectValue placeholder="选择数据库类型" />
          </SelectTrigger>
          <SelectContent>
            {capabilities.map((capability) => (
              <SelectItem key={capability.db_type} value={capability.db_type}>
                {capability.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2 md:col-span-2">
        <Label htmlFor="connector-description">用途描述</Label>
        <Textarea
          id="connector-description"
          value={form.description}
          onChange={(event) => onFormChange({ description: event.target.value })}
          placeholder="描述这个数据库连接器的用途，例如：生产环境订单库，只读账号，供报表查询使用"
          rows={2}
        />
        <p className="text-xs text-muted-foreground">纯文本描述，Agent 会通过此描述了解该库的用途。</p>
      </div>
    </div>
  );
}
