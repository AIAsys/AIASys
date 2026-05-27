export interface PreviewContribution {
  kind: string;
  component: string;
}

export interface ToolContribution {
  name: string;
  description: string;
}

export interface HookContribution {
  event: string;
  handler: string;
}
