export type DatabaseType = "postgres" | "mysql" | "influxdb3";
export type RuntimeDatabaseType = DatabaseType | "duckdb";
export type DatabaseFamily = "relational" | "timeseries";
export type ConnectionMode = "fields" | "url";
export type ConnectorTestStatus = "untested" | "passed" | "failed";
export type DatabaseGrant = "schema_read" | "data_read" | "data_write" | "ddl";
export type ApprovalPolicy = "none" | "manual";
export type DatabaseApiErrorCategory =
  | "auth"
  | "request"
  | "session"
  | "attachment"
  | "platform"
  | "approval"
  | "remote"
  | "remote_permission"
  | "remote_execution"
  | "runtime";

export interface DatabaseApiErrorDetail {
  code?: string | null;
  category?: DatabaseApiErrorCategory | null;
  message: string;
  retryable?: boolean | null;
}

export interface DatabaseConnectorShapeMeta {
  db_type: DatabaseType;
  connector_family?: DatabaseFamily | null;
  readonly_enforced?: boolean | null;
}

export interface DatabaseHandleCapabilityMetadata
  extends DatabaseConnectorShapeMeta {
  handle_kind?: "connector" | "builtin" | "query_only" | null;
  query_only?: boolean | null;
  supports_write?: boolean | null;
  supports_schema_inspection?: boolean | null;
}

export interface DatabaseConnectorCapability extends DatabaseConnectorShapeMeta {
  label: string;
  connection_modes: ConnectionMode[];
  readonly_enforced: boolean;
  driver_available: boolean;
  driver_name?: string | null;
  note?: string | null;
}

export interface DatabaseConnector extends DatabaseConnectorShapeMeta {
  connector_id: string;
  workspace_id?: string | null;
  scope: "global" | "workspace";
  name: string;
  connection_mode: ConnectionMode;
  host?: string | null;
  port?: number | null;
  database_name?: string | null;
  username?: string | null;
  description?: string | null;
  allow_notebook_access: boolean;
  allowed_schemas: string[];
  allowed_tables: string[];
  query_timeout_seconds: number;
  row_limit: number;
  has_password: boolean;
  has_api_token?: boolean;
  has_connection_url: boolean;
  password_masked?: string | null;
  api_token_masked?: string | null;
  connection_url_masked?: string | null;
  last_test_status: ConnectorTestStatus;
  last_test_message?: string | null;
  last_tested_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DatabaseConnectorDraftPayload extends DatabaseConnectorShapeMeta {
  name: string;
  connection_mode: ConnectionMode;
  host?: string | null;
  port?: number | null;
  database_name?: string | null;
  username?: string | null;
  password?: string | null;
  api_token?: string | null;
  connection_url?: string | null;
  description?: string | null;
  allow_notebook_access: boolean;
  allowed_schemas: string[];
  allowed_tables: string[];
  query_timeout_seconds: number;
  row_limit: number;
  scope?: "global" | "workspace";
}

export interface UpdateDatabaseConnectorPayload {
  name?: string;
  connection_mode?: ConnectionMode;
  host?: string | null;
  port?: number | null;
  database_name?: string | null;
  username?: string | null;
  password?: string | null;
  api_token?: string | null;
  connection_url?: string | null;
  description?: string | null;
  allow_notebook_access?: boolean;
  allowed_schemas?: string[];
  allowed_tables?: string[];
  query_timeout_seconds?: number;
  row_limit?: number;
  scope?: "global" | "workspace";
}

export interface DatabaseConnectorTestResult {
  success: boolean;
  db_type: DatabaseType;
  message: string;
  latency_ms?: number | null;
}

export interface SessionDatabaseAttachment extends DatabaseConnectorShapeMeta {
  session_id: string;
  connector_id: string;
  handle: string;
  name: string;
  handle_capability_metadata?: DatabaseHandleCapabilityMetadata | null;
  attached_at: string;
}

export interface BuiltinSessionDatabaseColumn {
  name: string;
  type: string;
  nullable: boolean;
  default: string | null;
}

export interface BuiltinSessionDatabaseTable {
  name: string;
  columns: BuiltinSessionDatabaseColumn[];
}

export interface BuiltinSessionDatabaseSchema {
  tables: BuiltinSessionDatabaseTable[];
}

export interface RuntimeDatabaseHandleInfo {
  handle: string;
  connector_id: string;
  name: string;
  db_type: RuntimeDatabaseType;
  grants: DatabaseGrant[];
  capability_upper_bound: DatabaseGrant[];
  approval_policy: ApprovalPolicy;
  attached_at: string;
}

export interface RuntimeDatabaseHandlesResponse {
  session_id: string;
  handles: RuntimeDatabaseHandleInfo[];
}

export interface RuntimeDatabaseQueryPayload {
  handle: string;
  sql: string;
  params?: unknown[] | Record<string, unknown> | null;
  limit?: number | null;
}

export interface RuntimeDatabaseQueryResponse {
  handle: string;
  audit_id: string | null;
  duration_ms: number | null;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  applied_limit: number | null;
}

export interface RuntimeDatabaseExecutePayload {
  handle: string;
  sql: string;
  params?: unknown[] | Record<string, unknown> | null;
}

export interface RuntimeDatabaseExecuteResponse {
  handle: string;
  audit_id: string | null;
  duration_ms: number | null;
  affected_rows: number;
  message: string | null;
}

export interface RuntimeDatabaseColumnInfo {
  name: string;
  type: string;
  nullable: boolean;
  default: string | null;
}

export interface RuntimeDatabaseListTablesResponse {
  handle: string;
  audit_id: string | null;
  duration_ms: number | null;
  tables: string[];
}

export interface RuntimeDatabaseDescribeTableResponse {
  handle: string;
  audit_id: string | null;
  duration_ms: number | null;
  table: string;
  columns: RuntimeDatabaseColumnInfo[];
}

export function getDatabaseTypeLabel(dbType: DatabaseType): string {
  switch (dbType) {
    case "postgres":
      return "PostgreSQL";
    case "mysql":
      return "MySQL";
    case "influxdb3":
      return "InfluxDB 3";
    default:
      return dbType;
  }
}

export function getRuntimeDatabaseTypeLabel(dbType: RuntimeDatabaseType): string {
  if (dbType === "duckdb") {
    return "DuckDB";
  }
  return getDatabaseTypeLabel(dbType);
}

export function resolveDatabaseFamily(
  source: DatabaseConnectorShapeMeta,
): DatabaseFamily {
  if (source.connector_family) {
    return source.connector_family;
  }
  return source.db_type === "influxdb3" ? "timeseries" : "relational";
}

export function isDatabaseConnectorQueryOnly(
  source:
    | DatabaseConnectorShapeMeta
    | {
        db_type: DatabaseType;
        handle_capability_metadata?: DatabaseHandleCapabilityMetadata | null;
      },
): boolean {
  const metadata =
    "handle_capability_metadata" in source
      ? source.handle_capability_metadata
      : null;

  if (metadata?.query_only === true) {
    return true;
  }
  if (metadata?.supports_write === false) {
    return true;
  }
  if (
    "readonly_enforced" in source &&
    typeof source.readonly_enforced === "boolean" &&
    source.readonly_enforced
  ) {
    return true;
  }
  return source.db_type === "influxdb3";
}

export function getDatabaseFamilyLabel(family: DatabaseFamily): string {
  return family === "timeseries" ? "时序" : "关系型";
}

export function runtimeHandleSupportsWrite(
  _handle: RuntimeDatabaseHandleInfo,
): boolean {
  // 权限完全由数据库原生账号控制，应用层不再判断
  return true;
}
