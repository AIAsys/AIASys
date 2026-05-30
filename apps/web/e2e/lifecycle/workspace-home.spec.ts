import { expect, test, type Page, type Response } from "@playwright/test";

import { registerLifecycleUser } from "./support";

function trackResponses(page: Page) {
  const responses: Response[] = [];
  page.on("response", (response) => {
    responses.push(response);
  });
  return responses;
}

function responseUrlsWithStatus(
  responses: Response[],
  matcher: (url: string) => boolean,
  status: number,
): string[] {
  return responses
    .filter((response) => response.status() === status && matcher(response.url()))
    .map((response) => response.url());
}

function responseUrlsMatching(
  responses: Response[],
  matcher: (url: string) => boolean,
): string[] {
  return responses
    .filter((response) => matcher(response.url()))
    .map((response) => response.url());
}

test.describe("Workspace home", () => {
  test("shows workspace home without session-scoped bootstrap requests", async ({
    page,
  }) => {
    await registerLifecycleUser(page.request);
    const responses = trackResponses(page);

    await page.goto("/workspace", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("工作区首页", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: "先选择一个工作区，再进入对应会话继续工作",
      }),
    ).toBeVisible();

    await page.waitForTimeout(1500);

    const sessionScopedRequests = responseUrlsMatching(responses, (url) =>
      url.includes("/api/sessions/status/") ||
      url.includes("/api/ask-user/pending?session_id=") ||
      url.includes("/api/mcp-session/") ||
      url.includes("/api/files/list/"),
    );

    expect(sessionScopedRequests).toEqual([]);
  });

  test("recovers invalid workspace route without resource 404s", async ({
    page,
  }) => {
    await registerLifecycleUser(page.request);
    const responses = trackResponses(page);
    const invalidWorkspaceId = "missing-workspace-demo";

    await page.goto(`/workspace?workspace_id=${invalidWorkspaceId}`, {
      waitUntil: "domcontentloaded",
    });

    await expect(page).toHaveURL("/workspace");
    await expect(page.getByText("工作区首页", { exact: true })).toBeVisible();
    await expect(page.getByText("最近工作区", { exact: true })).toBeVisible();

    await page.waitForTimeout(1500);

    const invalidWorkspace404s = responseUrlsWithStatus(
      responses,
      (url) => url.includes(invalidWorkspaceId),
      404,
    );
    expect(invalidWorkspace404s).toEqual([]);

    const leakedWorkspaceResourceRequests = responseUrlsMatching(
      responses,
      (url) =>
        url.includes(`/api/workspaces/${invalidWorkspaceId}`) ||
        url.includes(`/api/workspaces/${invalidWorkspaceId}/database-connectors`) ||
        url.includes(`/api/workspaces/${invalidWorkspaceId}/knowledge-bases`) ||
        url.includes(`/api/workspaces/${invalidWorkspaceId}/knowledge-graphs`),
    );
    expect(leakedWorkspaceResourceRequests).toEqual([]);
  });
});
