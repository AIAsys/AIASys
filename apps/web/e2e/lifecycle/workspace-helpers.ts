import { expect, type Page } from "@playwright/test";

export async function gotoWorkspaceSession(
  page: Page,
  sessionId: string,
  workspaceId?: string,
) {
  const query = workspaceId
    ? `workspace_id=${workspaceId}&session_id=${sessionId}`
    : `session_id=${sessionId}`;
  await page.goto(`/workspace?${query}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.locator("textarea")).toBeVisible();
}
