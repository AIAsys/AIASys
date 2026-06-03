import {
  getDatabaseTypeLabel,
} from "@/types/databaseConnectors";
import type {
  DatabaseConnector,
  DatabaseConnectorCapability,
  DatabaseConnectorDraftPayload,
  DatabaseType,
  UpdateDatabaseConnectorPayload,
} from "@/types/databaseConnectors";
import type { ConnectorFormState } from "./types";

export function createEmptyFormState(): ConnectorFormState {
  return {
    name: "",
    scope: "workspace",
    db_type: "postgres",
    host: "",
    port: "",
    database_name: "",
    username: "",
    password: "",
    description: "",
    allow_notebook_access: false,
  };
}

export function connectorToFormState(connector: DatabaseConnector): ConnectorFormState {
  return {
    name: connector.name,
    scope: connector.scope === "global" ? "global" : "workspace",
    db_type: connector.db_type,
    host: connector.host ?? "",
    port: connector.port ? String(connector.port) : "",
    database_name: connector.database_name ?? "",
    username: connector.username ?? "",
    password: "",
    description: connector.description ?? "",
    allow_notebook_access: connector.allow_notebook_access ?? false,
  };
}

export function parseNumberInput(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

export function buildDraftPayload(form: ConnectorFormState): DatabaseConnectorDraftPayload {
  const isInfluxDb3 = form.db_type === "influxdb3";
  return {
    name: form.name.trim(),
    scope: form.scope,
    db_type: form.db_type,
    connection_mode: "fields",
    host: form.host.trim() || null,
    port: parseNumberInput(form.port),
    database_name: form.database_name.trim() || null,
    username: isInfluxDb3 ? null : form.username.trim() || null,
    password: isInfluxDb3 ? null : form.password.trim() || null,
    api_token: isInfluxDb3 ? form.password.trim() || null : null,
    description: form.description.trim() || null,
    allow_notebook_access: form.allow_notebook_access,
    allowed_schemas: [],
    allowed_tables: [],
    query_timeout_seconds: 15,
    row_limit: 1000,
  };
}

export function buildUpdatePayload(form: ConnectorFormState): UpdateDatabaseConnectorPayload {
  const isInfluxDb3 = form.db_type === "influxdb3";
  const payload: UpdateDatabaseConnectorPayload = {
    name: form.name.trim(),
    scope: form.scope,
    connection_mode: "fields",
    host: form.host.trim() || null,
    port: parseNumberInput(form.port),
    database_name: form.database_name.trim() || null,
    username: isInfluxDb3 ? null : form.username.trim() || null,
    description: form.description.trim() || null,
    allow_notebook_access: form.allow_notebook_access,
    allowed_schemas: [],
    allowed_tables: [],
    query_timeout_seconds: 15,
    row_limit: 1000,
  };

  if (!isInfluxDb3 && form.password.trim()) {
    payload.password = form.password.trim();
  }
  if (isInfluxDb3 && form.password.trim()) {
    payload.api_token = form.password.trim();
  }

  return payload;
}

export function getSelectedCapability(
  capabilities: DatabaseConnectorCapability[],
  dbType: DatabaseType,
): DatabaseConnectorCapability | null {
  return capabilities.find((item) => item.db_type === dbType) ?? null;
}

export function getSelectedTypeLabel(dbType: DatabaseType): string {
  return getDatabaseTypeLabel(dbType);
}
