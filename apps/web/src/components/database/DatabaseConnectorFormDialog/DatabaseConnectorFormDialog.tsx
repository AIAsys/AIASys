import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  BasicInfoFields,
  ConnectionFields,
  FormHeader,
  FormInfoBox,
  FormFeedback,
  FormActions,
} from "./components";
import { useConnectorForm } from "./useConnectorForm";
import type { DatabaseConnectorFormDialogProps } from "./types";

type DatabaseConnectorFormContentProps = Pick<
  DatabaseConnectorFormDialogProps,
  "open" | "connector" | "capabilities" | "isSaving" | "onOpenChange" | "onSave" | "onTestDraft"
>;

export function DatabaseConnectorFormContent({
  open,
  connector,
  capabilities,
  isSaving,
  onOpenChange,
  onSave,
  onTestDraft,
}: DatabaseConnectorFormContentProps) {
  const {
    form,
    error,
    testResult,
    isTesting,
    isEditing,
    setForm,
    handleDbTypeChange,
    handleSave,
    handleTestDraft,
  } = useConnectorForm({
    open,
    connector,
    onSave,
    onTestDraft,
  });

  const handleFormChange = (updates: Partial<typeof form>) => {
    setForm((current) => ({ ...current, ...updates }));
  };

  return (
    <>
      <FormHeader isEditing={isEditing} />

      <div className="space-y-5">
        <FormInfoBox />

        <BasicInfoFields
          form={form}
          capabilities={capabilities}
          onDbTypeChange={handleDbTypeChange}
          onFormChange={handleFormChange}
        />

        <ConnectionFields
          form={form}
          connector={connector}
          onFormChange={handleFormChange}
        />

        <FormFeedback error={error} testResult={testResult} />
      </div>

      <DialogFooter>
        <FormActions
          isEditing={isEditing}
          isSaving={isSaving}
          isTesting={isTesting}
          onCancel={() => onOpenChange(false)}
          onTest={() => void handleTestDraft()}
          onSave={() => void handleSave()}
        />
      </DialogFooter>
    </>
  );
}

export function DatabaseConnectorFormDialog({
  open,
  connector,
  capabilities,
  isSaving,
  onOpenChange,
  onSave,
  onTestDraft,
  compact = false,
}: DatabaseConnectorFormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={compact ? "max-h-[90vh] max-w-2xl overflow-y-auto" : "max-h-[90vh] max-w-xl overflow-y-auto"}>
        <DialogHeader className="sr-only">
          <DialogTitle>数据库连接表单</DialogTitle>
          <DialogDescription>配置数据库连接参数，测试通过后方可使用。</DialogDescription>
        </DialogHeader>
        <DatabaseConnectorFormContent
          open={open}
          connector={connector}
          capabilities={capabilities}
          isSaving={isSaving}
          onOpenChange={onOpenChange}
          onSave={onSave}
          onTestDraft={onTestDraft}
        />
      </DialogContent>
    </Dialog>
  );
}
