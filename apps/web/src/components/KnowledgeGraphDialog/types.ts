export const KNOWLEDGE_GRAPH_DIALOG_TABS = [
  "workbench",
  "entities",
  "communities",
] as const;

export type KnowledgeGraphDialogTab =
  (typeof KNOWLEDGE_GRAPH_DIALOG_TABS)[number];

export function normalizeKnowledgeGraphDialogTab(
  value?: string | null,
): KnowledgeGraphDialogTab | null {
  if (!value) {
    return null;
  }

  if (
    value === "workbench" ||
    value === "entities" ||
    value === "communities"
  ) {
    return value;
  }

  return null;
}
