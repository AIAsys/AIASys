import type {
  DatabaseConnector,
  DatabaseConnectorCapability,
  DatabaseConnectorDraftPayload,
  DatabaseConnectorTestResult,
  DatabaseType,
  UpdateDatabaseConnectorPayload,
} from "@/types/databaseConnectors";

export interface DatabaseConnectorFormDialogProps {
  open: boolean;
  connector?: DatabaseConnector | null;
  capabilities: DatabaseConnectorCapability[];
  isSaving: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (
    payload: DatabaseConnectorDraftPayload | UpdateDatabaseConnectorPayload,
  ) => Promise<unknown>;
  onTestDraft: (
    payload: DatabaseConnectorDraftPayload,
  ) => Promise<DatabaseConnectorTestResult>;
  compact?: boolean;
}

export interface ConnectorFormState {
  name: string;
  scope: "global" | "workspace";
  db_type: DatabaseType;
  host: string;
  port: string;
  database_name: string;
  username: string;
  password: string;
  description: string;
  allow_notebook_access: boolean;
}

export interface FormValidationError {
  field?: string;
  message: string;
}

export interface UseConnectorFormReturn {
  form: ConnectorFormState;
  error: string | null;
  testResult: DatabaseConnectorTestResult | null;
  isTesting: boolean;
  isEditing: boolean;
  setForm: React.Dispatch<React.SetStateAction<ConnectorFormState>>;
  setError: (error: string | null) => void;
  handleDbTypeChange: (nextType: DatabaseType) => void;
  handleSave: () => Promise<void>;
  handleTestDraft: () => Promise<void>;
}
