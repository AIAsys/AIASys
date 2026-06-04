import { Plus, RefreshCw } from "lucide-react";
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { DatabaseConnectorFormDialog } from "@/components/database/DatabaseConnectorFormDialog";
import { testDatabaseConnectorDraft } from "@/lib/api/databaseConnectors";
import { ConnectorCard } from "./ConnectorCard";
import { ConnectorCardCompact } from "./ConnectorCardCompact";
import { DeleteConfirmDialog } from "./DeleteConfirmDialog";
import { EmptyState } from "./EmptyState";
import { LoadingState } from "./LoadingState";
import { SessionInfoCard } from "./SessionInfoCard";
import { UsageNote } from "./UsageNote";
import { useDatabaseConnectionsManager } from "./useDatabaseConnectionsManager";
import type { DatabaseConnectionsManagerPanelProps } from "./types";

export function DatabaseConnectionsManagerPanel({
  sessionId,
  workspaceId,
  onBackToSession,
  compact = false,
  openCreateOnMount = false,
  onRequestCreate,
}: DatabaseConnectionsManagerPanelProps) {
  const {
    connectors,
    capabilities,
    isLoading,
    error,
    notice,
    isDialogOpen,
    editingConnector,
    isSaving,
    testingConnectorId,
    deletingConnector,
    isDeleting,
    sessionActionKey,
    isUsageNoteOpen,
    expandedConnectorIds,
    setIsDialogOpen,
    setEditingConnector,
    setDeletingConnector,
    setIsUsageNoteOpen,
    toggleConnectorDetails,
    reload,
    handleSave,
    handleAttachToCurrentSession,
    handleDetachFromCurrentSession,
    handleTestConnector,
    handleDeleteConnector,
    openCreateDialog,
    openEditDialog,
    attachmentByConnectorId,
  } = useDatabaseConnectionsManager({ sessionId, workspaceId });
  const didOpenCreateOnMountRef = useRef(false);
  const handleCreateRequest = onRequestCreate ?? openCreateDialog;

  useEffect(() => {
    if (!openCreateOnMount || didOpenCreateOnMountRef.current) {
      return;
    }
    didOpenCreateOnMountRef.current = true;
    handleCreateRequest();
  }, [handleCreateRequest, openCreateOnMount]);

  return (
    <div className={compact ? "space-y-4 pb-1" : "space-y-6"}>
      <SessionInfoCard
        sessionId={sessionId}
        attachmentsCount={Array.from(attachmentByConnectorId.values()).length}
        onBackToSession={onBackToSession}
        compact={compact}
      />

      {error ? (
        <div className="rounded-lg border border-error/20 bg-error-container px-4 py-3 text-sm text-error">
          {error}
        </div>
      ) : null}

      {notice && !error ? (
        <div className="rounded-lg border border-success/20 bg-success-container px-4 py-3 text-sm text-success">
          {notice}
        </div>
      ) : null}

      <Card>
        <CardHeader className={compact ? "p-3" : undefined}>
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">已保存连接</CardTitle>
              {!compact ? (
                <CardDescription>
                  管理数据库连接配置。所有连接默认只读，写入权限由目标数据库账号自身控制。
                </CardDescription>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size={compact ? "sm" : "default"}
                onClick={reload}
                disabled={isLoading}
              >
                <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
                刷新
              </Button>
              <Button size={compact ? "sm" : "default"} onClick={handleCreateRequest}>
                <Plus className="h-4 w-4" />
                新建连接
              </Button>
            </div>
          </div>
          {compact ? <UsageNote isOpen={isUsageNoteOpen} onToggle={() => setIsUsageNoteOpen(!isUsageNoteOpen)} /> : null}
        </CardHeader>
        <CardContent className={compact ? "space-y-3 p-3" : "space-y-4"}>
          {isLoading ? <LoadingState /> : null}

          {!isLoading && connectors.length === 0 ? <EmptyState onCreate={handleCreateRequest} /> : null}

          {!isLoading &&
            connectors.map((connector) => {
              const currentAttachment = attachmentByConnectorId.get(connector.connector_id);
              const isDetailExpanded = expandedConnectorIds.has(connector.connector_id);

              if (compact) {
                return (
                  <ConnectorCardCompact
                    key={connector.connector_id}
                    connector={connector}
                    currentAttachment={currentAttachment}
                    sessionId={sessionId}
                    testingConnectorId={testingConnectorId}
                    sessionActionKey={sessionActionKey}
                    isDetailExpanded={isDetailExpanded}
                    onEdit={openEditDialog}
                    onDelete={setDeletingConnector}
                    onTest={handleTestConnector}
                    onAttach={handleAttachToCurrentSession}
                    onDetach={handleDetachFromCurrentSession}
                    onToggleDetails={toggleConnectorDetails}
                  />
                );
              }

              return (
                <ConnectorCard
                  key={connector.connector_id}
                  connector={connector}
                  currentAttachment={currentAttachment}
                  sessionId={sessionId}
                  testingConnectorId={testingConnectorId}
                  sessionActionKey={sessionActionKey}
                  compact={compact}
                  onEdit={openEditDialog}
                  onDelete={setDeletingConnector}
                  onTest={handleTestConnector}
                  onAttach={handleAttachToCurrentSession}
                  onDetach={handleDetachFromCurrentSession}
                />
              );
            })}
        </CardContent>
      </Card>

      <DatabaseConnectorFormDialog
        open={isDialogOpen}
        connector={editingConnector}
        capabilities={capabilities}
        isSaving={isSaving}
        onOpenChange={(open) => {
          setIsDialogOpen(open);
          if (!open) {
            setEditingConnector(null);
          }
        }}
        onSave={handleSave}
        onTestDraft={testDatabaseConnectorDraft}
      />

      <DeleteConfirmDialog
        deletingConnector={deletingConnector}
        isDeleting={isDeleting}
        onOpenChange={(open) => {
          if (!open) {
            setDeletingConnector(null);
          }
        }}
        onConfirm={handleDeleteConnector}
      />
    </div>
  );
}
