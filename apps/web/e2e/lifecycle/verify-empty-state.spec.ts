import { test, expect } from "@playwright/test";
import { randomUUID } from "crypto";

const API_BASE = "http://localhost:13001";
const FRONTEND_BASE = "http://localhost:13000";

async function createWorkspace() {
  const res = await fetch(`${API_BASE}/api/workspaces`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: `Empty-State-Test-${Date.now()}`,
      description: "Test workspace for empty state verification",
    }),
  });
  if (!res.ok) throw new Error(`createWorkspace failed: ${res.status}`);
  return (await res.json()) as { workspace_id: string };
}

async function createSession(workspaceId: string, title: string) {
  const sessionId = randomUUID();
  const res = await fetch(`${API_BASE}/api/sessions/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      workspace_id: workspaceId,
      title,
    }),
  });
  if (!res.ok) throw new Error(`createSession failed: ${res.status}`);
  return sessionId;
}

test("empty state should show session title instead of raw ID", async ({ page }) => {
  const ws = await createWorkspace();
  const sessionA = await createSession(ws.workspace_id, "第一个对话");

  await page.goto(
    `${FRONTEND_BASE}/analysis?workspace_id=${ws.workspace_id}&session_id=${sessionA}`,
    { waitUntil: "networkidle" },
  );
  await page.waitForTimeout(3000);

  const emptyStateText = page.locator("text=没有打开的文件");
  await expect(emptyStateText).toBeVisible({ timeout: 5000 });

  const branchLabel = page.locator("text=当前会话：");
  await expect(branchLabel).toBeVisible({ timeout: 5000 });

  // Verify session title is shown (not a raw UUID fragment)
  const idFragment = sessionA.slice(0, 8);
  const rawIdLabel = page.locator(`text=当前会话：${idFragment}`);
  await expect(rawIdLabel).not.toBeVisible();

  await page.screenshot({
    path: `/home/ke/projects/AIASys/.tmp/verify-empty-state.png`,
    fullPage: false,
  });
});

test("empty state should show recent conversations for workspace with multiple sessions", async ({ page }) => {
  // Use an existing workspace with 2+ conversations
  const workspaceId = "88e891ca-b690-47a8-b6a6-bd97a5c37e2d";
  const sessionId = "2fcd04df-a623-4a04-af9f-65abc2f606b8";

  await page.goto(
    `${FRONTEND_BASE}/analysis?workspace_id=${workspaceId}&session_id=${sessionId}`,
    { waitUntil: "networkidle" },
  );
  await page.waitForTimeout(4000);

  const emptyStateText = page.locator("text=没有打开的文件");
  await expect(emptyStateText).toBeVisible({ timeout: 5000 });

  // Session title should be shown
  const branchLabel = page.locator("text=当前会话：test");
  await expect(branchLabel).toBeVisible({ timeout: 5000 });

  // Recent conversations section should be visible
  const recentConv = page.locator("text=最近对话");
  await expect(recentConv).toBeVisible({ timeout: 5000 });

  await page.screenshot({
    path: `/home/ke/projects/AIASys/.tmp/verify-empty-state-with-recent.png`,
    fullPage: false,
  });
});
