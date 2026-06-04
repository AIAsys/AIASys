import { useCallback, useEffect, useState } from "react";
import { getErrorMessage } from "@/lib/utils";
import type { DatabaseConnectorTestResult, DatabaseType } from "@/types/databaseConnectors";
import type { DatabaseConnectorFormDialogProps, UseConnectorFormReturn } from "./types";
import {
  buildDraftPayload,
  buildUpdatePayload,
  connectorToFormState,
  createEmptyFormState,
} from "./formUtils";

export function useConnectorForm({
  open,
  connector,
  onSave,
  onTestDraft,
}: Pick<
  DatabaseConnectorFormDialogProps,
  "open" | "connector" | "onSave" | "onTestDraft"
>): UseConnectorFormReturn {
  const isEditing = Boolean(connector);
  const [form, setForm] = useState(createEmptyFormState());
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<DatabaseConnectorTestResult | null>(null);
  const [isTesting, setIsTesting] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }

    setForm(connector ? connectorToFormState(connector) : createEmptyFormState());
    setError(null);
    setTestResult(null);
    setIsTesting(false);
  }, [connector, open]);

  const handleDbTypeChange = useCallback(
    (nextType: DatabaseType) => {
      setForm((current) => ({
        ...current,
        db_type: nextType,
      }));
    },
    [],
  );

  const handleSave = useCallback(async () => {
    setError(null);

    try {
      if (isEditing) {
        await onSave(buildUpdatePayload(form));
      } else {
        await onSave(buildDraftPayload(form));
      }
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }, [isEditing, form, onSave]);

  const handleTestDraft = useCallback(async () => {
    setError(null);
    setTestResult(null);

    if (
      connector &&
      connector.has_password &&
      !form.password.trim()
    ) {
      setError("如需测试修改后的配置，请重新输入密码。");
      return;
    }

    setIsTesting(true);
    try {
      const result = await onTestDraft(buildDraftPayload(form));
      setTestResult(result);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsTesting(false);
    }
  }, [connector, form, onTestDraft]);

  return {
    form,
    error,
    testResult,
    isTesting,
    isEditing,
    setForm,
    setError,
    handleDbTypeChange,
    handleSave,
    handleTestDraft,
  };
}
