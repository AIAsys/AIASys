import { expect, test } from "@playwright/test";

import { createWorkspace, deleteWorkspace, registerLifecycleUser } from "./support";

test.describe("Expert policy settings", () => {
  test("sidebar collaboration experts entry opens settings dialog without route navigation", async ({
    page,
  }) => {
    const api = page.request;
    const workspace = await createWorkspace(api, {
      title: `协作专家弹窗回归-${Date.now()}`,
      mode: "analysis",
    });
    const initialGlobalPolicyResponse = await api.get("/api/experts/global/policy");
    const initialGlobalPolicy = (await initialGlobalPolicyResponse.json()) as {
      available_roles: Array<{
        role_id: string;
        catalog_visible: boolean;
        host_selectable: boolean;
        default_enabled: boolean;
      }>;
    };
    const initialReviewer = initialGlobalPolicy.available_roles.find(
      (role) => role.role_id === "reviewer",
    );
    const reviewerWasInstalled = Boolean(initialReviewer);
    if (!reviewerWasInstalled) {
      const installReviewerResponse = await api.post(
        "/api/experts/global/reviewer/enable",
        { data: { role_id: "reviewer" } },
      );
      expect(installReviewerResponse.ok()).toBeTruthy();
    }

    try {
      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        {
          waitUntil: "domcontentloaded",
        },
      );

      await expect
        .poll(() => new URL(page.url()).pathname)
        .toBe("/analysis");
      await expect
        .poll(() => new URL(page.url()).searchParams.get("workspace_id"))
        .toBe(workspace.workspaceId);

      await page.getByTestId("sidebar-workspace-tools-menu-trigger").click();
      await page.getByTestId("sidebar-workspace-tools-roles").click();

      await expect
        .poll(() => new URL(page.url()).pathname)
        .toBe("/analysis");
      await expect(
        page.getByTestId("collaboration-roles-settings-dialog"),
      ).toBeVisible();
      await expect(
        page.getByTestId("collaboration-roles-tab-aiasys"),
      ).toHaveAttribute("data-state", "active");
      await expect(
        page.getByTestId("collaboration-roles-tab-my-experts"),
      ).toBeVisible();
      await expect(
        page.getByTestId("collaboration-roles-tab-external"),
      ).toBeVisible();
      await expect(
        page.getByTestId("roles-manager-panel"),
      ).toHaveAttribute("data-scope", "global");

      await expect(
        page.getByRole("heading", { name: "AIASys 内置协作专家", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText("已安装到我的默认").first(),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "安装到当前工作区" }).first(),
      ).toBeVisible();
      await expect(page.getByTestId("roles-manager-create")).toHaveCount(0);

      await page.getByTestId("collaboration-roles-tab-my-experts").click();
      await expect(
        page.getByTestId("roles-manager-panel"),
      ).toHaveAttribute("data-scope", "global");
      await expect(page.getByTestId("role-visibility-trigger-reviewer")).toBeVisible();
      const reviewerDefaultToggle = page.getByTestId(
        "role-default-enabled-toggle-reviewer",
      );
      await expect(reviewerDefaultToggle).toBeVisible();
      const reviewerInitiallyEnabled = await reviewerDefaultToggle.isChecked();
      await reviewerDefaultToggle.locator("xpath=..").click();
      if (reviewerInitiallyEnabled) {
        await expect(reviewerDefaultToggle).not.toBeChecked();
      } else {
        await expect(reviewerDefaultToggle).toBeChecked();
      }
      await expect
        .poll(async () => {
          const response = await api.get("/api/experts/global/policy");
          const payload = (await response.json()) as {
            available_roles: Array<{
              role_id: string;
              default_enabled: boolean;
            }>;
          };
          return payload.available_roles.find(
            (role) => role.role_id === "reviewer",
          )?.default_enabled;
        })
        .toBe(!reviewerInitiallyEnabled);

      await page.getByTestId("role-remove-reviewer").click();
      await expect(
        page.getByText("内置源仍保留在市场里，可以重新安装。"),
      ).toBeVisible();
      const deleteRequest = page.waitForResponse((response) => {
        return (
          response.url().includes("/api/experts/global/reviewer") &&
          response.request().method() === "DELETE"
        );
      });
      await page.getByTestId("roles-manager-confirm-delete").click();
      const deleteResponse = await deleteRequest;
      expect(deleteResponse.ok()).toBeTruthy();
      await expect(page.getByTestId("role-remove-reviewer")).toHaveCount(0);
      await expect
        .poll(async () => {
          const response = await api.get("/api/experts/global/policy");
          const payload = (await response.json()) as {
            available_roles: Array<{ role_id: string }>;
          };
          return payload.available_roles.some((role) => role.role_id === "reviewer");
        })
        .toBe(false);

      await page.getByTestId("collaboration-roles-tab-aiasys").click();
      await expect(
        page.getByRole("button", { name: "安装到我的默认" }).first(),
      ).toBeVisible();

      await page.getByTestId("collaboration-roles-tab-external").click();
      await expect(
        page.getByTestId("external-collaboration-expert-market"),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "外部协作专家市场", exact: true }),
      ).toBeVisible();
    } finally {
      if (reviewerWasInstalled) {
        const restoreReviewerResponse = await api.post(
          "/api/experts/global/reviewer/enable",
          { data: { role_id: "reviewer" } },
        );
        if (restoreReviewerResponse.ok() && initialReviewer) {
          await api.put("/api/experts/global/reviewer/visibility", {
            data: {
              catalog_visible: initialReviewer.catalog_visible,
              host_selectable: initialReviewer.host_selectable,
              default_enabled: initialReviewer.default_enabled,
            },
          });
        }
      } else {
        await api.delete("/api/experts/global/reviewer");
      }
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("workspace experts catalog and workspace collaboration policy stay connected", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `协作专家回归-${Date.now()}`,
      mode: "analysis",
    });

    try {
      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        {
          waitUntil: "domcontentloaded",
        },
      );

      await expect
        .poll(async () => {
          const response = await api.get(
            `/api/workspaces/${workspace.workspaceId}/experts`,
          );
          const payload = (await response.json()) as {
            roles: Array<{ role_id: string }>;
          };
          return payload.roles.map((role) => role.role_id).join(",");
        })
        .toContain("data_analyst");

      await expect
        .poll(() => {
          return new URL(page.url()).searchParams.get("session_id");
        })
        .toBe(workspace.currentConversationId);

      const initialPolicyResponse = await api.put(
        `/api/workspaces/${workspace.workspaceId}/experts/policy`,
        {
          data: {
            enabled_role_ids: ["data_analyst", "researcher"],
          },
        },
      );
      expect(initialPolicyResponse.ok()).toBeTruthy();

      await page.getByRole("button", { name: "协作专家", exact: true }).click();

      const policySummary = page.getByTestId("workspace-expert-policy-summary");
      await expect(policySummary).toBeVisible();
      await expect(policySummary).toHaveAttribute(
        "data-workspace-id",
        workspace.workspaceId,
      );
      await policySummary.getByTestId("open-workspace-collaboration-settings").click();

      const policySurface = page.getByTestId("workspace-expert-policy-panel");
      await expect(
        policySurface,
      ).toBeVisible();
      await expect(policySurface).toHaveAttribute(
        "data-workspace-id",
        workspace.workspaceId,
      );

      await expect(
        page.getByRole("button", { name: "工作区协作配置", exact: true }),
      ).toBeVisible();

      await policySurface.getByRole("tab", { name: "协作专家" }).click();
      const researcherToggle = policySurface.getByTestId(
        "workspace-expert-role-toggle-researcher",
      );
      await researcherToggle.click();
      await expect(researcherToggle).toHaveAttribute("data-state", "unchecked");
      await policySurface.getByRole("tab", { name: "工具权限" }).click();
      const dataAnalystNotebookOutputTool = policySurface.getByTestId(
        "workspace-expert-role-tool-toggle-data_analyst-ReadNotebookOutputsTool",
      );
      await dataAnalystNotebookOutputTool.click({ force: true });
      await expect(dataAnalystNotebookOutputTool).toHaveAttribute("data-state", "unchecked");

      const saveRequest = page.waitForResponse((response) => {
        return (
          response
            .url()
            .includes(`/api/workspaces/${workspace.workspaceId}/experts/policy`) &&
          response.request().method() === "PUT"
        );
      });
      await policySurface.getByTestId("workspace-expert-policy-save").click();
      const saveResponse = await saveRequest;
      expect(saveResponse.ok()).toBeTruthy();

      await expect
        .poll(async () => {
          const response = await api.get(
            `/api/workspaces/${workspace.workspaceId}/experts/policy`,
          );
          const payload = (await response.json()) as {
            policy_mode: string;
            configured_enabled_role_ids: string[] | null;
            configured_role_tool_ids: Record<string, string[]> | null;
          };
          return JSON.stringify(payload);
        })
        .toContain('"policy_mode":"workspace"');
      await expect
        .poll(async () => {
          const response = await api.get(
            `/api/workspaces/${workspace.workspaceId}/experts/policy`,
          );
          const payload = (await response.json()) as {
            configured_enabled_role_ids: string[] | null;
          };
          return JSON.stringify(payload.configured_enabled_role_ids || []);
        })
        .not.toContain("researcher");
      await expect
        .poll(async () => {
          const response = await api.get(
            `/api/workspaces/${workspace.workspaceId}/experts/policy`,
          );
          const payload = (await response.json()) as {
            configured_role_tool_ids: Record<string, string[]> | null;
          };
          return JSON.stringify(payload.configured_role_tool_ids || {});
        })
        .not.toContain("ReadNotebookOutputsTool");

      await page.reload({ waitUntil: "domcontentloaded" });
      await page.getByRole("button", { name: "协作专家", exact: true }).click();
      await page
        .getByTestId("workspace-expert-policy-summary")
        .getByTestId("open-workspace-collaboration-settings")
        .click();

      const reloadedPolicySurface = page.getByTestId("workspace-expert-policy-panel");
      await expect(
        reloadedPolicySurface,
      ).toBeVisible();
      await reloadedPolicySurface.getByRole("tab", { name: "协作专家" }).click();
      await expect(
        reloadedPolicySurface
          .getByTestId("workspace-expert-role-toggle-researcher"),
      ).toHaveAttribute("data-state", "unchecked");
      await reloadedPolicySurface.getByRole("tab", { name: "工具权限" }).click();
      await expect(
        reloadedPolicySurface
          .getByTestId("workspace-expert-role-tool-toggle-data_analyst-ReadNotebookOutputsTool"),
      ).toHaveAttribute("data-state", "unchecked");

      await page.keyboard.press("Escape");
      await expect(
        page.getByRole("button", { name: "协作节点", exact: true }),
      ).toBeVisible();
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("workspace visibility switch hides non selectable roles from workspace policy", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `协作专家可见性回归-${Date.now()}`,
      mode: "analysis",
    });

    try {
      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        {
          waitUntil: "domcontentloaded",
        },
      );

      const installResponse = await api.post(
        `/api/workspaces/${workspace.workspaceId}/experts/coder/enable`,
        {
          data: { role_id: "coder" },
        },
      );
      expect(installResponse.ok()).toBeTruthy();
      const installReviewerResponse = await api.post(
        `/api/workspaces/${workspace.workspaceId}/experts/reviewer/enable`,
        {
          data: { role_id: "reviewer" },
        },
      );
      expect(installReviewerResponse.ok()).toBeTruthy();

      await page.getByRole("button", { name: "协作专家", exact: true }).click();
      await expect(page.getByTestId("role-visibility-trigger-coder")).toBeVisible();
      await page.getByTestId("role-visibility-trigger-coder").click();

      const popover = page.getByTestId("role-visibility-popover-coder");
      await expect(popover).toBeVisible();
      const hostSelectable = popover.getByTestId(
        "role-visibility-host-selectable-coder",
      );
      await expect(hostSelectable).toBeChecked();
      await hostSelectable.locator("xpath=..").click();
      await expect(hostSelectable).not.toBeChecked();

      const saveRequest = page.waitForResponse((response) => {
        return (
          response.url().includes(
            `/api/workspaces/${workspace.workspaceId}/experts/coder/visibility`,
          ) && response.request().method() === "PUT"
        );
      });
      await popover.getByTestId("role-visibility-save-coder").click();
      const saveResponse = await saveRequest;
      expect(saveResponse.ok()).toBeTruthy();

      await expect
        .poll(async () => {
          const response = await api.get(
            `/api/workspaces/${workspace.workspaceId}/experts`,
          );
          const payload = (await response.json()) as {
            roles: Array<{
              role_id: string;
              host_selectable: boolean;
              default_enabled: boolean;
            }>;
          };
          const coder = payload.roles.find((role) => role.role_id === "coder");
          return `${coder?.host_selectable}:${coder?.default_enabled}`;
        })
        .toBe("false:false");

      await page
        .getByTestId("workspace-expert-policy-summary")
        .getByTestId("open-workspace-collaboration-settings")
        .click();

      const policySurface = page.getByTestId("workspace-expert-policy-panel");
      await expect(policySurface).toBeVisible();
      await policySurface.getByRole("tab", { name: "协作专家" }).click();
      await expect(
        policySurface.getByTestId("workspace-expert-role-toggle-coder"),
      ).toHaveCount(0);
      await expect(
        policySurface.getByTestId("workspace-expert-role-toggle-reviewer"),
      ).toBeVisible();

      const rejected = await api.put(
        `/api/workspaces/${workspace.workspaceId}/experts/policy`,
        {
          data: {
            enabled_role_ids: ["coder"],
          },
        },
      );
      expect(rejected.status()).toBe(400);
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
