import { copyFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { Document, Packer, Paragraph, TextRun } from "docx";
import { expect, test } from "@playwright/test";
import * as XLSX from "xlsx";

import {
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";

const BACKEND_WORKSPACES_ROOT = path.resolve(
  process.cwd(),
  "../backend/data/workspaces",
);
const REPO_ROOT = path.resolve(process.cwd(), "../..");

async function writeWorkspaceBinaryFile(options: {
  userId: string;
  workspaceId: string;
  fileName: string;
  content: Buffer;
}) {
  const targetPath = path.join(
    BACKEND_WORKSPACES_ROOT,
    options.userId,
    options.workspaceId,
    "workspace",
    options.fileName,
  );
  await mkdir(path.dirname(targetPath), { recursive: true });
  await writeFile(targetPath, options.content);
}

async function copyWorkspaceFixture(options: {
  userId: string;
  workspaceId: string;
  sourcePath: string;
  fileName: string;
}) {
  const targetPath = path.join(
    BACKEND_WORKSPACES_ROOT,
    options.userId,
    options.workspaceId,
    "workspace",
    options.fileName,
  );
  await mkdir(path.dirname(targetPath), { recursive: true });
  await copyFile(options.sourcePath, targetPath);
}

async function buildDocxFixture() {
  const doc = new Document({
    sections: [
      {
        children: [
          new Paragraph({
            children: [
              new TextRun({
                text: "Word preview browser smoke marker",
                bold: true,
              }),
            ],
          }),
          new Paragraph("这是浏览器驱动验收用的 docx 文件。"),
        ],
      },
    ],
  });

  return await Packer.toBuffer(doc);
}

function buildXlsxFixture() {
  const workbook = XLSX.utils.book_new();
  const worksheet = XLSX.utils.aoa_to_sheet([
    ["Name", "Value"],
    ["Excel preview browser smoke marker", "passed"],
  ]);
  XLSX.utils.book_append_sheet(workbook, worksheet, "SmokeSheet");

  return XLSX.write(workbook, {
    bookType: "xlsx",
    type: "buffer",
  }) as Buffer;
}

test.describe("Workspace file preview browser smoke", () => {
  test.setTimeout(180_000);

  test("PDF, Excel, Word and PPT open in the workspace assets preview", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    const api = page.request;
    const user = await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `浏览器回归-文件预览-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "文件预览会话",
    });

    const files = {
      pdf: "browser-preview.pdf",
      xlsx: "browser-preview.xlsx",
      docx: "browser-preview.docx",
      pptx: "browser-preview.pptx",
    };

    try {
      await writeWorkspaceBinaryFile({
        userId: user.userId,
        workspaceId: workspace.workspaceId,
        fileName: files.docx,
        content: await buildDocxFixture(),
      });
      await writeWorkspaceBinaryFile({
        userId: user.userId,
        workspaceId: workspace.workspaceId,
        fileName: files.xlsx,
        content: buildXlsxFixture(),
      });
      await copyWorkspaceFixture({
        userId: user.userId,
        workspaceId: workspace.workspaceId,
        sourcePath: path.join(
          REPO_ROOT,
          "archive/06-docs-and-references/reference_frameworks/others/haystack/e2e/samples/sample_pdf_1.pdf",
        ),
        fileName: files.pdf,
      });
      await copyWorkspaceFixture({
        userId: user.userId,
        workspaceId: workspace.workspaceId,
        sourcePath: path.join(
          REPO_ROOT,
          "archive/06-docs-and-references/reference_frameworks/others/haystack/test/test_files/pptx/sample_pptx.pptx",
        ),
        fileName: files.pptx,
      });

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );
      await expect(page.locator("textarea")).toBeVisible();

      const fileTab = page.locator("button[aria-label='文件']");
      if (await fileTab.isVisible()) {
        await fileTab.click();
      } else {
        await page.getByRole("button", { name: "资产", exact: true }).click();
      }
      const panel = page.locator('[data-testid="workspace-artifacts-panel"]');
      await expect(panel).toBeVisible();

      for (const fileName of Object.values(files)) {
        await expect(panel.getByText(fileName, { exact: true })).toBeVisible();
      }

      const openInMainCanvas = async (fileName: string) => {
        await panel
          .getByRole("button", {
            name: `打开 ${fileName} 的文件操作菜单`,
            exact: true,
          })
          .click();
        await page.getByRole("menuitem", { name: "在主画布打开" }).click();
        await expect(
          page.getByRole("heading", { name: fileName }),
        ).toBeVisible();
      };

      await openInMainCanvas(files.pdf);
      const pdfFrame = page.locator(`iframe[title="${files.pdf}"]`);
      await expect(pdfFrame).toBeAttached();
      await expect
        .poll(async () => await pdfFrame.getAttribute("src"))
        .toContain("disposition=inline");
      await page.screenshot({
        path: testInfo.outputPath("file-preview-pdf.png"),
        fullPage: true,
      });

      await openInMainCanvas(files.xlsx);
      await expect(
        page.getByText("Excel preview browser smoke marker", { exact: true }),
      ).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath("file-preview-excel.png"),
        fullPage: true,
      });

      await openInMainCanvas(files.docx);
      await expect(
        page.getByText("Word preview browser smoke marker", { exact: true }),
      ).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath("file-preview-word.png"),
        fullPage: true,
      });

      await openInMainCanvas(files.pptx);
      await expect(page.getByText("PPT 预览加载失败")).toHaveCount(0);
      await expect(page.getByText("文件过大，无法预览")).toHaveCount(0);
      await expect(
        page.locator(".pptx-preview-wrapper, .slide").first(),
      ).toBeVisible();
      await expect(page.getByText("产物信息", { exact: true })).toHaveCount(0);
      await page.getByRole("button", { name: "查看文件信息" }).click();
      await expect(page.getByText("产物信息", { exact: true })).toBeVisible();
      await expect(page.getByText("来源运行", { exact: true })).toBeVisible();
      await expect(page.getByText("版本记录", { exact: true })).toBeVisible();
      await page.getByRole("button", { name: "关闭文件信息" }).click();
      await expect(page.getByText("产物信息", { exact: true })).toHaveCount(0);
      await expect(
        page.locator(".pptx-preview-wrapper, .slide").first(),
      ).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath("file-preview-ppt.png"),
        fullPage: true,
      });
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
