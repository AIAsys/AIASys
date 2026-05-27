import type {
  DatabaseConnectorDraftPayload,
  UpdateDatabaseConnectorPayload,
} from "@/types/databaseConnectors";

export interface DatabaseConnectionsManagerPanelProps {
  sessionId?: string | null;
  onBackToSession?: (() => void) | null;
  compact?: boolean;
  openCreateOnMount?: boolean;
  onRequestCreate?: (() => void) | null;
}

export type SavePayload = DatabaseConnectorDraftPayload | UpdateDatabaseConnectorPayload;
