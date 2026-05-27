---
version: alpha
name: AIASys Workspace Console
description: AIASys 当前主线的视觉设计基线。面向 agent、设计审查和前端实现，用来稳定任务工作区、对象画布、助手侧栏、设置弹层和资源目录的共同视觉语言。
colors:
  background: "#F6F7FA"
  on-background: "#101828"
  surface: "#FFFFFF"
  surface-dim: "#F1F4F8"
  surface-container: "#E9EEF5"
  surface-container-high: "#DCE3EC"
  surface-overlay: "#F9FAFB"
  on-surface: "#0F172A"
  on-surface-variant: "#667085"
  primary: "#111827"
  on-primary: "#FFFFFF"
  primary-container: "#E5E7EB"
  on-primary-container: "#1F2937"
  secondary: "#CBD5E1"
  on-secondary: "#0F172A"
  secondary-container: "#EEF2F7"
  on-secondary-container: "#334155"
  tertiary: "#2563EB"
  on-tertiary: "#FFFFFF"
  tertiary-container: "#DBEAFE"
  on-tertiary-container: "#1D4ED8"
  success: "#0F766E"
  on-success: "#FFFFFF"
  success-container: "#CCFBF1"
  on-success-container: "#115E59"
  warning: "#B54708"
  on-warning: "#FFFFFF"
  warning-container: "#FEF0C7"
  on-warning-container: "#93370D"
  error: "#B42318"
  on-error: "#FFFFFF"
  error-container: "#FEE4E2"
  on-error-container: "#912018"
  info: "#026AA2"
  on-info: "#FFFFFF"
  info-container: "#D1E9FF"
  on-info-container: "#075985"
  outline: "#D0D5DD"
  outline-variant: "#E4E7EC"
  focus: "#2563EB"
  sidebar: "#F3F5F9"
  on-sidebar: "#0F172A"
  muted: "#F8FAFC"
  on-muted: "#475467"
typography:
  title-xl:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: "650"
    lineHeight: 36px
    letterSpacing: -0.02em
  title-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: "600"
    lineHeight: 32px
    letterSpacing: -0.015em
  title-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: "600"
    lineHeight: 28px
  heading-sm:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: "600"
    lineHeight: 24px
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: "400"
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: "400"
    lineHeight: 22px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: "400"
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: "600"
    lineHeight: 16px
    letterSpacing: 0.02em
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: "700"
    lineHeight: 14px
    letterSpacing: 0.08em
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: "500"
    lineHeight: 16px
rounded:
  xs: 4px
  sm: 6px
  md: 10px
  lg: 14px
  xl: 20px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
  rail-width: 320px
  sidebar-width: 264px
  shell-padding: 24px
  panel-gap: 20px
components:
  workspace-shell:
    backgroundColor: "{colors.background}"
    textColor: "{colors.on-background}"
    padding: "{spacing.shell-padding}"
  left-navigation:
    backgroundColor: "{colors.sidebar}"
    textColor: "{colors.on-sidebar}"
    rounded: "{rounded.xl}"
    padding: "{spacing.lg}"
    width: "{spacing.sidebar-width}"
  object-canvas:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.xl}"
    padding: "{spacing.xl}"
  assistant-rail:
    backgroundColor: "{colors.surface-overlay}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.xl}"
    padding: "{spacing.lg}"
    width: "{spacing.rail-width}"
  panel-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
  panel-muted:
    backgroundColor: "{colors.surface-dim}"
    textColor: "{colors.on-surface-variant}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  panel-section:
    backgroundColor: "{colors.surface-container}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  panel-section-strong:
    backgroundColor: "{colors.surface-container-high}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  muted-strip:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.on-muted}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    height: 36px
    padding: 0 14px
  button-primary-hover:
    backgroundColor: "{colors.on-primary-container}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    height: 36px
    padding: 0 14px
  button-secondary:
    backgroundColor: "{colors.primary-container}"
    textColor: "{colors.on-primary-container}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    height: 36px
    padding: 0 14px
  button-accent:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.on-tertiary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.md}"
    height: 36px
    padding: 0 14px
  accent-chip:
    backgroundColor: "{colors.tertiary-container}"
    textColor: "{colors.on-tertiary-container}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  neutral-chip:
    backgroundColor: "{colors.secondary-container}"
    textColor: "{colors.on-secondary-container}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  toolbar-toggle:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.on-secondary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  input-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  sidebar-item:
    backgroundColor: "{colors.sidebar}"
    textColor: "{colors.on-surface-variant}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  sidebar-item-active:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  divider-muted:
    backgroundColor: "{colors.outline-variant}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.xs}"
    padding: "{spacing.xs}"
  divider-strong:
    backgroundColor: "{colors.outline}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.xs}"
    padding: "{spacing.xs}"
  focus-ring:
    backgroundColor: "{colors.focus}"
    textColor: "{colors.on-tertiary}"
    rounded: "{rounded.full}"
    padding: "{spacing.xs}"
  status-success:
    backgroundColor: "{colors.success-container}"
    textColor: "{colors.on-success-container}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  status-success-strong:
    backgroundColor: "{colors.success}"
    textColor: "{colors.on-success}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  status-warning:
    backgroundColor: "{colors.warning-container}"
    textColor: "{colors.on-warning-container}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  status-warning-strong:
    backgroundColor: "{colors.warning}"
    textColor: "{colors.on-warning}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  status-error:
    backgroundColor: "{colors.error-container}"
    textColor: "{colors.on-error-container}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  status-error-strong:
    backgroundColor: "{colors.error}"
    textColor: "{colors.on-error}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  status-info:
    backgroundColor: "{colors.info-container}"
    textColor: "{colors.on-info-container}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  status-info-strong:
    backgroundColor: "{colors.info}"
    textColor: "{colors.on-info}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  code-inline:
    backgroundColor: "{colors.surface-container}"
    textColor: "{colors.on-surface}"
    typography: "{typography.code-sm}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xs}"
---

# AIASys Design Baseline

## Overview

AIASys 的界面服务长期任务工作区。用户进入系统时，核心任务是组织资料、推进分支、调用能力、检查产物和继续协作。视觉设计必须先保证这些动作清楚、稳定、可持续使用。

整体气质是冷静、清楚、工具化、证据优先。界面不靠强品牌色和大面积装饰制造记忆点，而是靠稳定的工作骨架、清楚的面板边界、可扫描的信息层级和少量语义色建立秩序。

主界面默认采用三段式骨架：左侧是工作区与分支导航，中间是当前对象画布，右侧是当前任务协作与上下文。右侧栏不默认承接完整执行流，不长期展示大段日志，不和中间主画布抢主语义。

当前 `/analysis` 主壳按单机单用户工作台设计。左侧是工作区导航，中间主画布默认显示 `工作区`，右侧是当前分支侧栏。`工作区` 内部导航以当前代码和最新文档为准，主语收口到 `概览 / 资源 / 能力 / 自动化 / 资产` 这一组工作区对象。`数据工作台` 从 `资源` 里的数据库资源进入，作为打开对象承接 SQL、表、查询结果、附件和保存视图。右侧只服务当前分支的对话、输入、分支切换和托管循环。

视觉参考优先使用真实浏览器截图、当前代码和 `design/frontend/界面设计/工作区壳层/` 下的 Markdown 语义文档。旧 AI 生成图、旧静态稿和旧 Pencil 原型只保留追溯价值。新生成概念图必须注明参考来源和有效范围，不能自动成为实现基线。

AIASys 当前不设计多人协作产品形态。界面里不要出现成员在线、邀请成员、多人头像协同等团队 SaaS 语义。这里的“协作”指用户与 Agent、子 Agent、托管循环之间的任务协作。

## Colors

颜色只服务结构、状态和可操作重点。默认页面使用中性浅底，前景内容用白色或近白色面板承载，边界用低饱和灰蓝色建立层级。强调色保持克制，不能让每个模块都拥有独立品牌色。

- **Background (#F6F7FA):** 页面底色。用于多面板控制台，保证长时间阅读时不刺眼。
- **Surface (#FFFFFF):** 主内容面。用于对象画布、卡片、弹层和输入区。
- **Surface Dim (#F1F4F8):** 次级面。用于摘要区、折叠区和弱提示容器。
- **Primary (#111827):** 主操作和关键结构锚点。它承担确定性，弱化装饰感。
- **Tertiary (#2563EB):** 少量链接、当前选中能力、关键引导和聚焦操作。一个视图内不要大量使用。
- **Outline (#D0D5DD):** 普通边界。边框应该清楚，但不把界面切得很硬。
- **Success / Warning / Error / Info:** 只用于执行状态、资源可用性、风险和验证结果。

深色模式可以存在，默认设计基线以浅色为主。深色模式应沿用同样的信息结构，不能变成另一个视觉产品。

## Typography

排版优先服务高密度工作。标题要让用户定位当前对象，正文要便于扫读，标签和状态要紧凑，路径、命令、ID 和运行值要使用等宽字体降低误读。

- **Title XL / LG / MD:** 用于页面标题、当前对象标题和大面板标题。字号克制，不使用海报式大标题。
- **Heading SM:** 用于面板内小标题、分组标题和列表区标题。
- **Body LG / MD / SM:** 用于说明、列表、配置项和对话周边信息。默认优先 `body-md`。
- **Label MD / Label Caps:** 用于按钮、状态、筛选器、短标签和顶部元信息。全大写标签只用于极少量系统级分组，不用于正文。
- **Code SM:** 用于路径、命令、ID、变量名、模型名和运行态值。

默认字体是 Inter 和 Noto Sans SC 的组合，技术信息使用 JetBrains Mono。不要用花哨字体建立风格，也不要为单个页面引入独立字体体系。

## Layout

AIASys 的主界面围绕“当前任务工作区”组织。布局优先回答四个问题：用户在哪，当前主对象是什么，下一步常用操作是什么，哪些信息是证据。

左侧导航承接工作区、分支、最小系统入口和局部目录。它应稳定、可折叠、可扫描，不承接复杂配置正文。

中间主画布承接当前活跃对象。对象可以是文件、Notebook、数据库、PDF、图表、知识图谱、执行产物或工作区目录。一个时刻只能有一个主对象拥有视觉主语义。

`资源` 是工作区内部的固定入口，用于查看当前工作区可见资源、可查询数据源和运行时可用性。`数据工作台` 从资源里的数据库资源打开，不作为工作区同级大页签。Notebook、PDF、图片、HTML、图表和保存视图按对象实例打开，不进入固定顶层工作面。

右侧助手侧栏承接当前任务协作、输入、上下文摘要和当前对象的轻量说明。执行详情、日志、资源验证结果和诊断信息通过抽屉、弹层或次级入口进入，不长期占据右侧一级区域。

设置类界面统一采用左侧导航和右侧内容。左侧负责分组，右侧负责当前分组的说明、表单、开关和保存动作。内容区需要独立滚动，不能让整个页面或弹层一起跳动。

间距以 4px 和 8px 节奏为基础。工作区页面允许中高密度，但必须有摘要、折叠和局部展开策略。不要把工作台做成大量留白的展示页。

## Elevation & Depth

层级主要通过底色、边框、圆角和内容密度建立。阴影只作为辅助，不承担主要结构表达。

- **Base:** `background` 承接整个工作环境。
- **Primary Surface:** `surface` 承接主对象、卡片和弹层。
- **Secondary Surface:** `surface-dim` 和 `surface-container` 承接摘要、分组和弱强调。
- **Overlay:** `surface-overlay` 用于抽屉、右栏局部浮层和轻弹层。

普通面板不要使用强阴影。弹层可以比卡片略强，但仍应保持工具系统的克制感。玻璃拟态、霓虹、重渐变和大面积模糊不适合作为 AIASys 的主视觉基线。

## Shapes

圆角用于降低长期工作界面的锐利感，并保持面板层级统一。

- **4px / 6px:** 细分隔、内联代码、小型标签。
- **10px:** 输入框、按钮、列表项、紧凑卡片。
- **14px:** 常规面板和内容卡片。
- **20px:** 主画布、侧栏外壳、较大的弹层容器。
- **Full:** 状态胶囊、筛选胶囊和小型元信息。

同一个页面内不要混用过多圆角等级。圆角不能替代信息结构，如果面板关系不清楚，先调整分组和边界。

## Components

### Workspace Shell

工作区外壳使用中性浅底，给左侧导航、中间对象画布和右侧助手侧栏提供稳定承载。它不使用大面积装饰性渐变，也不把页面做成宣传页。

### Left Navigation

左侧导航负责工作区、分支、目录和少量系统入口。默认背景轻于主画布，激活态用白色面和更高文本对比突出。列表项需要紧凑，支持折叠，避免在左侧解释复杂架构。

### Object Canvas

对象画布是视觉主语义。它承接当前正在查看、编辑、执行或分析的对象。画布内可以有二级导航，但不能让右栏或顶部状态抢走主对象的位置。

### Assistant Rail

助手侧栏承接当前任务协作。它显示输入区、当前对象摘要、少量上下文和必要状态。长日志、完整执行流、数据库管理页和市场页面不作为右栏常驻内容。

### Panel Card

卡片用于承接结构化信息。卡片要边界清楚、内容密度适中、标题明确。高密度卡片必须有摘要或折叠策略。

### Action Elements

主按钮使用 `primary`，表示当前视图里最确定、最主要的动作。次按钮使用浅色容器。强调按钮使用 `tertiary`，只在需要引导用户注意时使用。一个局部区域内不要同时出现多个强按钮。

### Inputs

输入框保持白底、清楚边界和稳定文本层级。输入区应避免过度装饰。涉及命令、路径、模型、变量时使用等宽字体或内联代码样式。

### Status Pills

状态胶囊用于执行中、成功、警告、失败、信息提示。状态色面积要小，语义要清楚。不要用状态色给模块分区。

### Settings Surfaces

设置、工作区设置、当前分支设置和用户默认设置都采用“左侧分组、右侧内容”的结构。当前设置层级必须在界面上可见，避免把系统目录层、用户默认层、任务工作层混成一张表单。

## Do's and Don'ts

### Do

- 保持工作区、分支、当前对象和助手侧栏的主次关系清楚。
- 使用中性底色、稳定边界、轻层次面板和少量语义色。
- 让高密度页面具备摘要、折叠和局部展开。
- 把路径、命令、ID、模型名和运行值当成技术信息处理。
- 让设置类界面保持左侧导航和右侧内容的稳定骨架。
- 在 agent 生成页面前读取本文件，并优先服从这里的视觉基线。

### Don't

- 不要把 AIASys 做成营销页、品牌秀场或大面积装饰性渐变页面。
- 不要为每个模块发明独立品牌色。
- 不要让执行日志、诊断详情或市场目录长期占据右侧一级主区。
- 不要把内部迁移说明、治理规则和架构解释直接渲染到用户界面。
- 不要用强阴影、玻璃拟态和霓虹色来替代信息分层。
- 不要在没有适配脚本时把本文件的 Tailwind 导出直接覆盖现有 Tailwind 4 变量体系。
- 不要把空状态做成无操作的死页面，也不要在异常状态只抛错误码不给下一步。
- 不要让表格横向滚动超出视口，核心列和操作必须在首屏可见。
