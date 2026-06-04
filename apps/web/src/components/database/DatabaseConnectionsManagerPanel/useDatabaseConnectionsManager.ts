import { useCallback, useEffect, useMemo, useState } from "react";
import {
  attachDatabaseConnector,
  createDatabaseConnector,
  deleteDatabaseConnector,
  detachDatabaseConnector,
  getDatabaseConnectorErrorMessage,
  listDatabaseConnectorCapabilities,
  listDatabaseConnectors,
  listSessionDatabaseAttachments,
  testSavedDatabaseConnector,
  updateDatabaseConnector,
} from "@/lib/api/databaseConnectors";
import {
  emitDatabaseConnectorSync,
  subscribeDatabaseConnectorSync,
} from "@/lib/databaseConnectorEvents";
import type {
  DatabaseConnector,
  DatabaseConnectorCapability,
  DatabaseConnectorDraftPayload,
  SessionDatabaseAttachment,
  UpdateDatabaseConnectorPayload,
} from "@/types/databaseConnectors";

interface UseDatabaseConnectionsManagerOptions {
  sessionId?: string | null;
  workspaceId?: string | null;
}

export function useDatabaseConnectionsManager({ sessionId, workspaceId }: UseDatabaseConnectionsManagerOptions) {
  const [reloadToken, setReloadToken] = useState(0);
  const [connectors, setConnectors] = useState<DatabaseConnector[]>([]);
  const [attachments, setAttachments] = useState<SessionDatabaseAttachment[]>([]);
  const [capabilities, setCapabilities] = useState<DatabaseConnectorCapability[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingConnector, setEditingConnector] = useState<DatabaseConnector | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [testingConnectorId, setTestingConnectorId] = useState<string | null>(null);
  const [deletingConnector, setDeletingConnector] = useState<DatabaseConnector | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [sessionActionKey, setSessionActionKey] = useState<string | null>(null);
  const [isUsageNoteOpen, setIsUsageNoteOpen] = useState(false);
  const [expandedConnectorIds, setExpandedConnectorIds] = useState<Set<string>>(new Set());

  // 加载数据
  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      setIsLoading(true);
      setError(null);

      try {
        const [capabilityList, connectorList, attachmentList] = await Promise.all([
          listDatabaseConnectorCapabilities(),
          listDatabaseConnectors(workspaceId ?? undefined),
          sessionId ? listSessionDatabaseAttachments(sessionId) : Promise.resolve([]),
        ]);

        if (cancelled) {
          return;
        }

        setCapabilities(capabilityList);
        setConnectors(connectorList);
        setAttachments(attachmentList);
      } catch (err) {
        if (cancelled) {
          return;
        }
        setError(getDatabaseConnectorErrorMessage(err, "加载数据库连接失败"));
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadData();

    return () => {
      cancelled = true;
    };
  }, [reloadToken, sessionId]);

  // 订阅同步事件
  useEffect(() => {
    return subscribeDatabaseConnectorSync(() => {
      setReloadToken((current) => current + 1);
    });
  }, []);

  const attachmentByConnectorId = useMemo(
    () => new Map(attachments.map((attachment) => [attachment.connector_id, attachment])),
    [attachments],
  );

  const reload = useCallback(() => {
    setReloadToken((current) => current + 1);
  }, []);

  const openCreateDialog = useCallback(() => {
    setEditingConnector(null);
    setIsDialogOpen(true);
    setError(null);
    setNotice(null);
  }, []);

  const openEditDialog = useCallback((connector: DatabaseConnector) => {
    setEditingConnector(connector);
    setIsDialogOpen(true);
    setError(null);
    setNotice(null);
  }, []);

  const persistConnector = useCallback(
    async (
      payload: DatabaseConnectorDraftPayload | UpdateDatabaseConnectorPayload,
    ): Promise<DatabaseConnector> => {
      setIsSaving(true);
      try {
        const savedConnector = editingConnector
          ? await updateDatabaseConnector(
              editingConnector.connector_id,
              payload as UpdateDatabaseConnectorPayload,
            )
          : await createDatabaseConnector(
              payload as DatabaseConnectorDraftPayload,
              workspaceId ?? undefined,
            );
        setIsDialogOpen(false);
        setEditingConnector(null);
        return savedConnector;
      } finally {
        setIsSaving(false);
      }
    },
    [editingConnector],
  );

  const handleSave = useCallback(
    async (payload: DatabaseConnectorDraftPayload | UpdateDatabaseConnectorPayload) => {
      const isEditing = Boolean(editingConnector);
      await persistConnector(payload);
      setNotice(isEditing ? "数据库连接已更新。" : "数据库连接已创建。");
      emitDatabaseConnectorSync({ scope: "connectors", sessionId });
      setReloadToken((current) => current + 1);
    },
    [editingConnector, persistConnector, sessionId],
  );

  const handleAttachToCurrentSession = useCallback(
    async (connector: DatabaseConnector) => {
      if (!sessionId) {
        return;
      }
      setError(null);
      setNotice(null);
      setSessionActionKey(`attach:${connector.connector_id}`);
      try {
        await attachDatabaseConnector(sessionId, connector.connector_id);
        setNotice(`「${connector.name}」已附加到当前会话。`);
        emitDatabaseConnectorSync({ scope: "attachments", sessionId });
        setReloadToken((current) => current + 1);
      } catch (err) {
        setError(getDatabaseConnectorErrorMessage(err, "附加数据库连接失败"));
      } finally {
        setSessionActionKey(null);
      }
    },
    [sessionId],
  );

  const handleDetachFromCurrentSession = useCallback(
    async (connector: DatabaseConnector) => {
      if (!sessionId) {
        return;
      }
      setError(null);
      setNotice(null);
      setSessionActionKey(`detach:${connector.connector_id}`);
      try {
        await detachDatabaseConnector(sessionId, connector.connector_id);
        setNotice(`「${connector.name}」已从当前会话卸载。`);
        emitDatabaseConnectorSync({ scope: "attachments", sessionId });
        setReloadToken((current) => current + 1);
      } catch (err) {
        setError(getDatabaseConnectorErrorMessage(err, "卸载数据库连接失败"));
      } finally {
        setSessionActionKey(null);
      }
    },
    [sessionId],
  );

  const handleTestConnector = useCallback(
    async (connector: DatabaseConnector) => {
      setTestingConnectorId(connector.connector_id);
      setError(null);
      setNotice(null);
      try {
        const result = await testSavedDatabaseConnector(connector.connector_id);
        setNotice(
          `「${connector.name}」${result.success ? "测试通过" : "测试失败"}：${result.message}`,
        );
        emitDatabaseConnectorSync({ scope: "connectors", sessionId });
        setReloadToken((current) => current + 1);
      } catch (err) {
        setError(getDatabaseConnectorErrorMessage(err, "测试数据库连接失败"));
      } finally {
        setTestingConnectorId(null);
      }
    },
    [sessionId],
  );

  const handleDeleteConnector = useCallback(async () => {
    if (!deletingConnector) {
      return;
    }

    setIsDeleting(true);
    setError(null);
    setNotice(null);

    try {
      await deleteDatabaseConnector(deletingConnector.connector_id);
      setNotice(`「${deletingConnector.name}」已删除。`);
      setDeletingConnector(null);
      emitDatabaseConnectorSync({ scope: "connectors", sessionId });
      setReloadToken((current) => current + 1);
    } catch (err) {
      setError(getDatabaseConnectorErrorMessage(err, "删除数据库连接失败"));
    } finally {
      setIsDeleting(false);
    }
  }, [deletingConnector, sessionId]);

  const toggleConnectorDetails = useCallback((connectorId: string) => {
    setExpandedConnectorIds((prev) => {
      const next = new Set(prev);
      if (next.has(connectorId)) {
        next.delete(connectorId);
      } else {
        next.add(connectorId);
      }
      return next;
    });
  }, []);

  return {
    connectors,
    attachments,
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
    setError,
    setNotice,
    reload,
    handleSave,
    handleAttachToCurrentSession,
    handleDetachFromCurrentSession,
    handleTestConnector,
    handleDeleteConnector,
    openCreateDialog,
    openEditDialog,
    attachmentByConnectorId,
  };
}
