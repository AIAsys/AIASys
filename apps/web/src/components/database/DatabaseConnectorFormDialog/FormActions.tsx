import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface FormActionsProps {
  isEditing: boolean;
  isSaving: boolean;
  isTesting: boolean;
  onCancel: () => void;
  onTest: () => void;
  onSave: () => void;
}

export function FormActions({
  isEditing,
  isSaving,
  isTesting,
  onCancel,
  onTest,
  onSave,
}: FormActionsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="outline" onClick={onCancel} disabled={isSaving || isTesting}>
        取消
      </Button>
      <Button
        variant="outline"
        onClick={onTest}
        disabled={isSaving || isTesting}
      >
        {isTesting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        测试连接
      </Button>
      <Button onClick={onSave} disabled={isSaving || isTesting}>
        {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        {isEditing ? "保存修改" : "创建连接"}
      </Button>
    </div>
  );
}
