/**
 * AIASys 统一扩展注册表
 *
 * 提供预览渲染器、Agent 工具、生命周期钩子等扩展能力的注册与查找。
 */

import type { ComponentType } from "react";
import type { HookContribution, ToolContribution } from "@/types/extension";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PreviewContribution {
  kind: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- 预览组件 props 类型各异，无法统一约束
  component: ComponentType<any>;
  label?: string;
}

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

class ExtensionRegistry {
  private previews = new Map<string, PreviewContribution>();
  private tools = new Map<string, ToolContribution>();
  private hooks = new Map<string, HookContribution>();

  // -- Preview renderers --

  registerPreview(
    kind: string,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- 预览组件 props 类型各异
    component: ComponentType<any>,
    label?: string,
  ): void {
    this.previews.set(kind, { kind, component, label });
  }

  getPreview(kind: string): PreviewContribution | undefined {
    return this.previews.get(kind);
  }

  hasPreview(kind: string): boolean {
    return this.previews.has(kind);
  }

  getRegisteredPreviewKinds(): string[] {
    return Array.from(this.previews.keys());
  }

  // -- Agent tools --

  registerTool(tool: ToolContribution): void {
    this.tools.set(tool.name, tool);
  }

  unregisterTool(name: string): void {
    this.tools.delete(name);
  }

  replaceTools(tools: ToolContribution[]): void {
    this.tools.clear();
    tools.forEach((tool) => this.registerTool(tool));
  }

  getTool(name: string): ToolContribution | undefined {
    return this.tools.get(name);
  }

  hasTool(name: string): boolean {
    return this.tools.has(name);
  }

  getRegisteredTools(): ToolContribution[] {
    return Array.from(this.tools.values());
  }

  // -- Lifecycle hooks --

  registerHook(hook: HookContribution): void {
    this.hooks.set(`${hook.event}:${hook.handler}`, hook);
  }

  unregisterHook(event: string, handler: string): void {
    this.hooks.delete(`${event}:${handler}`);
  }

  replaceHooks(hooks: HookContribution[]): void {
    this.hooks.clear();
    hooks.forEach((hook) => this.registerHook(hook));
  }

  getHook(event: string): HookContribution | undefined {
    return Array.from(this.hooks.values()).find((hook) => hook.event === event);
  }

  hasHook(event: string): boolean {
    return Array.from(this.hooks.values()).some((hook) => hook.event === event);
  }

  getRegisteredHooks(): HookContribution[] {
    return Array.from(this.hooks.values());
  }
}

export const extensionRegistry = new ExtensionRegistry();
