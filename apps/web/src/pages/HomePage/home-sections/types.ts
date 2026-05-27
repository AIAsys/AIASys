import type { ComponentType } from "react";

export type StatusTone = "ready" | "beta" | "planned";
export type SectionTone = "light" | "dark";

export type CapabilityCard = {
  title: string;
  summary: string;
  icon: ComponentType<{ className?: string }>;
  accent: string;
  glow: string;
  features: Array<{
    label: string;
    status: string;
    tone: StatusTone;
  }>;
  note: string;
};

export type ScenarioCard = {
  title: string;
  summary: string;
  icon: ComponentType<{ className?: string }>;
  steps: string[];
  outcome: string;
};

export type WorkflowStep = {
  title: string;
  detail: string;
  icon: ComponentType<{ className?: string }>;
};

export type TrustCard = {
  title: string;
  tone: StatusTone;
  summary: string;
  items: string[];
};

export type SurfacePreviewKind = "analysis" | "knowledge" | "graph" | "skills";

export type SurfacePreviewCard = {
  title: string;
  route: string;
  summary: string;
  bullets: string[];
  kind: SurfacePreviewKind;
  actionLabel: string;
  onClick: (isAuthenticated: boolean) => void;
};

export type EntryCard = {
  title: string;
  description: string;
  action: string;
  onClick: (isAuthenticated: boolean) => void;
};
