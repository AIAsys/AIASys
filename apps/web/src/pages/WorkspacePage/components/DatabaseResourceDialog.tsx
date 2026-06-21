import { useEffect, useState } from "react";
import { PlugZap } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  FileUploadToast,
  useFileUploadToast,
} from "@/components/file/FileUploadToast";
import { DatabaseConnectionsManagerPanel } from "@/components/database/DatabaseConnectionsManagerPanel";
import {
  DatabaseConnectorFormContent,
} from "@/components/database/DatabaseConnectorFormDialog/DatabaseConnectorFormDialog";
import {
  createDatabaseConnector,
  listDatabaseConnectorCapabilities,
  testDatabaseConnectorDraft,
} from "@/lib/api/databaseConnectors";
import { emitDatabaseConnectorSync } from "@/lib/databaseConnectorEvents";
import type {
  DatabaseConnectorDraftPayload,
  DatabaseConnectorCapability,
  UpdateDatabaseConnectorPayload,
} from "@/types/databaseConnectors";
import type {
  DatabaseResourceDialogAction,
  DatabaseResourceDialogTab,
} from "../hooks/useWorkspaceOverlayState";

interface DatabaseResourceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultTab?: DatabaseResourceDialogTab;
  defaultAction?: DatabaseResourceDialogAction;
  sessionId?: string | null;
}

export function DatabaseResourceDialog({
  open,
  onOpenChange,
  defaultTab = "catalog",
  defaultAction = "manage",
  sessionId,
}: DatabaseResourceDialogProps) {
  const { toasts, showError } = useFileUploadToast();
  const [activeTab, setActiveTab] = useState<DatabaseResourceDialogTab>(defaultTab);
  const [activeAction, setActiveAction] =
    useState<DatabaseResourceDialogAction>(defaultAction);
  const [capabilities, setCapabilities] = useState<DatabaseConnectorCapability[]>([]);
  const [isSaving, setIsSaving] = useState(false);

  const isCreateMode = activeAction === "create";

  useEffect(() => {
    if (!open) {
      return;
    }
    setActiveTab(defaultTab);
    setActiveAction(defaultAction);
  }, [defaultAction, defaultTab, open]);

  useEffect(() => {
    if (!open || !isCreateMode) {
      return;
    }
    let cancelled = false;
    void listDatabaseConnectorCapabilities()
      .then((items) => {
        if (!cancelled) {
          setCapabilities(items);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCapabilities([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [isCreateMode, open]);

  const handleCreateSave = async (
    payload: DatabaseConnectorDraftPayload | UpdateDatabaseConnectorPayload,
  ) => {
    setIsSaving(true);
    try {
      await createDatabaseConnector(payload as DatabaseConnectorDraftPayload);
      emitDatabaseConnectorSync({ scope: "connectors", sessionId });
      onOpenChange(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "创建数据库连接失败";
      showError(message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={
          isCreateMode
            ? "max-h-[90vh] max-w-2xl overflow-y-auto"
            : "flex h-[88vh] max-w-[min(1320px,94vw)] flex-col overflow-hidden p-0"
        }
      >
        {!isCreateMode ? (
          <>
            <DialogTitle className="sr-only">数据库管理</DialogTitle>
            <DialogDescription className="sr-only">
              在分析页内单独管理数据库连接目录。
            </DialogDescription>
          </>
        ) : null}

        {!isCreateMode ? (
          <>
            <div className="border-b bg-muted/20 px-6 py-5 pr-12">
              <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <PlugZap className="h-4 w-4 text-muted-foreground" />
                    数据库管理
                  </div>
                  <div className="mt-1 text-xs leading-5 text-muted-foreground">
                    这里管理全局数据库连接资源；创建后的连接可以被多个工作区复用。
                  </div>
                </div>
              </div>
            </div>

            {activeTab === "catalog" ? (
              <div className="min-h-0 flex-1 overflow-y-auto p-6">
                <DatabaseConnectionsManagerPanel
                  sessionId={sessionId}
                  compact
                  onRequestCreate={() => setActiveAction("create")}
                />
              </div>
            ) : null}
          </>
        ) : (
          <div>
            <DatabaseConnectorFormContent
              open={open}
              connector={null}
              capabilities={capabilities}
              isSaving={isSaving}
              onOpenChange={onOpenChange}
              onSave={handleCreateSave}
              onTestDraft={testDatabaseConnectorDraft}
            />
          </div>
        )}
        {toasts.map((toast) => (
          <FileUploadToast
            key={toast.id}
            message={toast.message}
            type={toast.type}
          />
        ))}
      </DialogContent>
    </Dialog>
  );
}
