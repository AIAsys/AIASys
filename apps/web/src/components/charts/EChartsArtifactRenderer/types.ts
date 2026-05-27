export type JsonRecord = Record<string, unknown>;

export interface ChartDataset {
  mode?: string;
  type?: string;
  source?: unknown;
  fileRef?: string;
  uri?: string;
}

export interface ChartResource {
  resourceId?: string;
  kind?: string;
  fileRef?: string;
  uri?: string;
}

export interface ChartArtifact {
  kind?: string;
  type?: string;
  version?: number;
  engine?: string;
  mode?: string;
  meta?: JsonRecord;
  view?: JsonRecord;
  dataset?: ChartDataset;
  resources?: ChartResource[];
  interaction?: JsonRecord;
  payload?: JsonRecord;
  spec?: JsonRecord;
  fallback?: JsonRecord;
}

export interface MapRegistration {
  mapName: string;
  geoJson: unknown;
}

export interface RenderPlan {
  option: JsonRecord;
  mapRegistrations: MapRegistration[];
  renderer: "canvas" | "svg";
  title?: string;
  description?: string;
}

export interface ChartExportController {
  canExportPng: boolean;
  exportPng: (filename?: string) => void;
}

export interface EChartsArtifactRendererProps {
  artifactPath?: string;
  artifactContent?: string;
  sessionId?: string;
  token?: string;
  variant?: "chat" | "workspace";
  className?: string;
}
