import { expect, test } from "@playwright/test";

import {
  buildAnalysisUrl,
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";

test.describe("AutoTask run-now browser regression", () => {
  test.setTimeout(120_000);

  test("auto task run-now creates a new branch and updates task state", async ({
    page,
  }) => {
    const api = page.request;
    await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: "浏览器回归-自动任务立即运行",
      initialConversationTitle: "自动任务主控会话",
    });

    try {
      await page.goto(
        buildAnalysisUrl({
          workspaceId: workspace.workspaceId,
          conversationId: workspace.currentConversationId,
        }),
        {
          waitUntil: "domcontentloaded",
        },
      );

      await expect(page.locator("textarea")).toBeVisible();
      await page.getByRole("button", { name: "自动化任务", exact: true }).click();
      await expect(page.getByText("当前工作区还没有自动化任务")).toBeVisible();

      const createResponse = await api.post(
        `/api/auto-tasks/workspaces/${workspace.workspaceId}/tasks`,
        {
          data: {
            title: "浏览器回归-自动任务立即运行",
            prompt: "请简短回复 done。",
            trigger_type: "interval",
            trigger_value: "3600",
            first_run_policy: "next_scheduled",
            sandbox_mode: "local",
            mode: "analysis",
            overlap_policy: "skip",
            session_strategy: "new_each_time",
          },
        },
      );
      expect(createResponse.ok()).toBeTruthy();
      const created = (await createResponse.json()) as {
        task_id: string;
        first_run_policy?: string;
      };
      expect(created.first_run_policy).toBe("next_scheduled");

      await page.getByRole("button", { name: "刷新" }).click();
      const taskRow = page.locator("section").filter({
        hasText: "浏览器回归-自动任务立即运行",
      }).first();
      await expect(taskRow).toBeVisible();
      await expect(page.getByText("等待计划时间").first()).toBeVisible();
      await expect(taskRow.getByText("触发", { exact: true })).toBeVisible();
      await expect(taskRow.getByText("每次新建会话")).toBeVisible();
      await expect
        .poll(async () => {
          return page
            .getByText("等待计划时间")
            .first()
            .evaluate((node) => node.getBoundingClientRect().width);
        })
        .toBeGreaterThan(64);

      await taskRow.getByRole("button", { name: "立即运行" }).click();

      await expect
        .poll(
          async () => {
            const response = await api.get(
              `/api/auto-tasks/workspaces/${workspace.workspaceId}/tasks`,
            );
            if (!response.ok()) {
              return 0;
            }
            const body = (await response.json()) as {
              tasks?: Array<{ task_id: string; fired_count?: number }>;
            };
            return body.tasks?.find((task) => task.task_id === created.task_id)
              ?.fired_count ?? 0;
          },
          {
            timeout: 90_000,
          },
        )
        .toBeGreaterThan(0);

      await expect
        .poll(
          async () => {
            const response = await api.get(`/api/workspaces/${workspace.workspaceId}`);
            if (!response.ok()) {
              return 0;
            }
            const body = (await response.json()) as {
              conversation_count?: number;
            };
            return body.conversation_count ?? 0;
          },
          {
            timeout: 90_000,
          },
        )
        .toBeGreaterThan(1);
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
