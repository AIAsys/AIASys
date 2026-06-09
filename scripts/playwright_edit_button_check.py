#!/usr/bin/env python3
"""
Playwright script to verify the "编辑并重发" (edit and resend) button
on user messages in the AIASys conversation dock.
"""

import asyncio
from playwright.async_api import async_playwright

TARGET_URL = "http://localhost:13000"
WORKSPACE_NAME = "README 演示 - 销售洞察分析"
OUTPUT_PATH = "/home/ke/projects/AIASys/design-draft/quality-assurance/2026-06-09-conversation-dock-review/screenshots/edit-button-check.png"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--window-size=1400,900"])
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        print(f"1. Opening {TARGET_URL} ...")
        await page.goto(TARGET_URL, wait_until="networkidle")
        await asyncio.sleep(1)

        # Click "开始分析" to get to workspace/dashboard
        print("1a. Clicking '开始分析' to enter app...")
        start_btn = page.locator("text=开始分析").first
        if await start_btn.count() > 0:
            await start_btn.click()
            await asyncio.sleep(2)

        # Try to find the workspace card and click it
        print(f"2. Looking for workspace '{WORKSPACE_NAME}' ...")
        workspace_card = page.locator(f"text={WORKSPACE_NAME}").first
        if await workspace_card.count() > 0:
            print("   Found workspace card, clicking...")
            await workspace_card.click()
        else:
            print("   Workspace card not found.")
            await browser.close()
            return None

        print("3. Waiting for workspace to load...")
        await asyncio.sleep(3)

        print("4. Looking for user messages and revealing edit button...")
        
        # Find user messages - look for the specific message content we saw
        msg_text_content = "请分析当前工作区里的销售数据"
        msg_locator = page.locator(f"text={msg_text_content}").first
        if await msg_locator.count() > 0:
            print(f"   Found user message containing '{msg_text_content}'")
            await msg_locator.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            
            # Hover over the message to reveal action buttons
            parent = msg_locator.locator("xpath=../..").first
            if await parent.count() > 0:
                await parent.hover()
                await asyncio.sleep(1)
            
            await msg_locator.hover()
            await asyncio.sleep(1)

            # Try to find and hover the edit button (pencil icon) specifically
            # Look for buttons near the user message
            edit_btn = page.locator("text=编辑并重发").first
            if await edit_btn.count() > 0:
                print("   Found '编辑并重发' button, hovering over it...")
                await edit_btn.scroll_into_view_if_needed()
                await edit_btn.hover()
                await asyncio.sleep(2)  # Wait for tooltip to appear
            else:
                # Look for any button with pencil icon or edit-related
                all_btns = page.locator("button").all()
                for btn in all_btns:
                    txt = await btn.inner_text()
                    if "编辑" in txt or "重发" in txt:
                        print(f"   Found button with text: {txt}")
                        await btn.scroll_into_view_if_needed()
                        await btn.hover()
                        await asyncio.sleep(2)
                        break
        else:
            print("   User message not found with text search")

        print("5. Taking screenshot of chat area...")
        # Screenshot the right sidebar area
        await page.screenshot(path=OUTPUT_PATH, clip={"x": 750, "y": 0, "width": 650, "height": 900})

        print(f"6. Screenshot saved to: {OUTPUT_PATH}")
        await browser.close()
        return OUTPUT_PATH

if __name__ == "__main__":
    result = asyncio.run(main())
    print(f"Done: {result}")
