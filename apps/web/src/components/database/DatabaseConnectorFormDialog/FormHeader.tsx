import { PlugZap } from "lucide-react";
import {
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface FormHeaderProps {
  isEditing: boolean;
}

export function FormHeader({ isEditing }: FormHeaderProps) {
  return (
    <DialogHeader>
      <DialogTitle className="flex items-center gap-2">
        <PlugZap className="h-4 w-4" />
        {isEditing ? "编辑数据库连接" : "新建数据库连接"}
      </DialogTitle>
      <DialogDescription>
        填写目标数据库的连接信息。平台仅开放只读查询，写入操作由目标数据库账号自身权限控制。
      </DialogDescription>
    </DialogHeader>
  );
}
