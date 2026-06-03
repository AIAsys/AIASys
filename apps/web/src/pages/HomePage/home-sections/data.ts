import {
  Blocks,
  Bot,
  BrainCircuit,
  Database,
  FileArchive,
  FileStack,
  FolderKanban,
  GitBranch,
  Library,
  Network,
  ScanSearch,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { goToWorkspace } from "../navigation";
import type {
  CapabilityCard,
  EntryCard,
  ScenarioCard,
  SurfacePreviewCard,
  TrustCard,
  WorkflowStep,
} from "./types";

export const surfacePreviewCards: SurfacePreviewCard[] = [
  {
    title: "分析主链路",
    route: "/workspace",
    summary:
      "从一个具体问题出发，Host Agent 自动拆解为子任务，多 Agent 并行执行，全程可视化追踪。",
    bullets: [
      "复杂任务自动分解，Sub Agent 并行推进",
      "右侧边栏实时展示执行流与工具调用",
      "文件、结果、导出材料集中沉淀",
    ],
    kind: "analysis",
    actionLabel: "进入分析工作台",
    onClick: () => goToWorkspace("knowledge_base"),
  },
  {
    title: "知识库",
    route: "/workspace?overlay=knowledge_base",
    summary:
      "在分析过程中随时调取知识库——上传文档、检索内容、把可用资源挂载到当前任务。",
    bullets: [
      "分析页内一键打开，无需跳转",
      "工作区仅消费已挂载的知识库",
      "知识库与图谱均以内嵌弹窗承载",
    ],
    kind: "knowledge",
    actionLabel: "在分析中打开",
    onClick: () => goToWorkspace("knowledge_base"),
  },
  {
    title: "知识图谱探索",
    route: "/workspace?overlay=knowledge_graph",
    summary:
      "把零散信息连成关系网络，用 GraphRAG 在实体之间穿行，快速定位关键脉络。",
    bullets: [
      "以关系视角理解信息结构",
      "GraphRAG 实体关系自由浏览",
      "内嵌图谱弹窗，不打断分析节奏",
    ],
    kind: "graph",
    actionLabel: "在分析中探索",
    onClick: () => goToWorkspace("knowledge_graph"),
  },
  {
    title: "技能市场",
    route: "/workspace",
    summary:
      "在分析工作台中浏览、安装技能，装完即刻生效，无需重启或切换页面。",
    bullets: [
      "分析页内打开技能市场弹窗",
      "安装即用，零等待",
      "支持自定义开发专属技能",
    ],
    kind: "skills",
    actionLabel: "在分析中使用",
    onClick: () => goToWorkspace(),
  },
];

export const capabilityCards: CapabilityCard[] = [
  {
    title: "多 Agent 并行执行",
    summary:
      "Host Agent 将复杂任务拆解为子任务，多个 Sub Agent 同时推进，显著缩短交付时间。",
    icon: Bot,
    accent: "from-slate-950 via-indigo-800 to-violet-600",
    glow: "bg-foreground/10",
    features: [
      { label: "Host + 多 Sub Agent 并行架构", status: "已可用", tone: "ready" },
      { label: "任务自动分解与并行调度", status: "已可用", tone: "ready" },
      { label: "右侧执行流实时可视化", status: "已可用", tone: "ready" },
    ],
    note: "不是一次问答，而是一支并行推进的 Agent 编队。",
  },
  {
    title: "会话化分析",
    summary:
      "围绕真实任务展开多轮对话，SSE 流式响应配合人工确认，不把复杂分析压扁成单次问答。",
    icon: BrainCircuit,
    accent: "from-slate-950 via-slate-800 to-slate-600",
    glow: "bg-foreground/10",
    features: [
      { label: "SSE 流式执行与实时响应", status: "已可用", tone: "ready" },
      { label: "会话历史续聊与状态恢复", status: "已可用", tone: "ready" },
      { label: "AskUser 人机协同确认", status: "已可用", tone: "ready" },
    ],
    note: "分析的深度来自持续对话，而非一次性提示词。",
  },
  {
    title: "能力与工具接入",
    summary:
      "连接器、技能、知识库统一接入同一工作面，工具调用全程可观测、可追溯。",
    icon: Wrench,
    accent: "from-slate-950 via-lime-900 to-emerald-700",
    glow: "bg-success/10",
    features: [
      { label: "连接器工具动态接入", status: "已可用", tone: "ready" },
      { label: "技能运行时调用", status: "已可用", tone: "ready" },
      { label: "工具调用详情追踪", status: "已可用", tone: "ready" },
    ],
    note: "接入只是起点，纳入执行闭环并被治理才是关键。",
  },
  {
    title: "工作区与资产沉淀",
    summary:
      "对话中产生的数据、代码、图表和中间结果自动归入工作区，让复盘和交接有据可依。",
    icon: FolderKanban,
    accent: "from-zinc-900 via-zinc-700 to-stone-500",
    glow: "bg-stone-900/10",
    features: [
      { label: "文件上传、列表、下载与删除", status: "已可用", tone: "ready" },
      { label: "Markdown / DOCX / PDF 单文件导出", status: "已可用", tone: "ready" },
      { label: "会话级审计导出", status: "已可用", tone: "ready" },
    ],
    note: "适合需要保留中间产物、审查记录和交接材料的团队场景。",
  },
  {
    title: "本地执行",
    summary:
      "代码和查询默认在你的机器上运行，数据不出本地，专注打磨任务工作区的核心体验。",
    icon: ShieldCheck,
    accent: "from-slate-950 via-cyan-900 to-blue-700",
    glow: "bg-info/10",
    features: [
      { label: "本地 Python / IPython 执行链路", status: "已可用", tone: "ready" },
      { label: "任务内执行记录追踪", status: "已可用", tone: "ready" },
      { label: "默认本地执行路径", status: "已可用", tone: "ready" },
    ],
    note: "先做稳、做透单机体验，再谈扩展。",
  },
  {
    title: "知识能力栈",
    summary:
      "知识库管理、文档检索、知识图谱探索——全部内嵌在分析工作台中，无缝衔接分析流程。",
    icon: Network,
    accent: "from-slate-950 via-sky-900 to-cyan-700",
    glow: "bg-info/10",
    features: [
      { label: "分析页面内管理知识库", status: "已可用", tone: "ready" },
      { label: "GraphRAG 知识图谱探索", status: "已可用", tone: "ready" },
      { label: "统一文档提取与向量化", status: "已可用", tone: "ready" },
    ],
    note: "知识库与图谱使用独立路由页承接，任务工作区负责挂载、切换和回到执行上下文。",
  },
  {
    title: "数据库浏览器",
    summary:
      "在会话中直连 PostgreSQL 等数据库，浏览表结构、执行 SQL、沉淀查询结果，一气呵成。",
    icon: Database,
    accent: "from-slate-950 via-violet-900 to-purple-700",
    glow: "bg-info/10",
    features: [
      { label: "PostgreSQL 连接与表结构查看", status: "已可用", tone: "ready" },
      { label: "SQL 查询执行与结果展示", status: "已可用", tone: "ready" },
      { label: "MySQL/SQLite 多数据库支持", status: "已可用", tone: "ready" },
    ],
    note: "把数据查询和分析整合进同一个工作台，无需切换工具。",
  },
  {
    title: "技能市场",
    summary:
      "在分析工作台中浏览、安装技能，装完即用，让领域知识变成可复用的能力组件。",
    icon: Library,
    accent: "from-slate-950 via-amber-900 to-yellow-600",
    glow: "bg-warning/10",
    features: [
      { label: "分析页面内技能浏览与安装", status: "已可用", tone: "ready" },
      { label: "自定义技能开发", status: "已可用", tone: "ready" },
      { label: "安装即刻在会话中使用", status: "已可用", tone: "ready" },
    ],
    note: "让领域专家的知识变成可复用的技能组件，在分析页面一键安装使用。",
  },
  {
    title: "可复核交付",
    summary:
      "过程、结果、边界一目了然，不只剩一张截图——对话记录、工作区产物、导出材料完整留存。",
    icon: FileArchive,
    accent: "from-slate-950 via-amber-900 to-orange-700",
    glow: "bg-warning/10",
    features: [
      { label: "对话记录导出", status: "已可用", tone: "ready" },
      { label: "工作区导出与留痕", status: "已可用", tone: "ready" },
      { label: "Markdown/DOCX/PDF 多格式导出", status: "已可用", tone: "ready" },
    ],
    note: "交付的价值不在于'得到了答案'，而在于答案经得起复核和交接。",
  },
];

export const scenarioCards: ScenarioCard[] = [
  {
    title: "多 Agent 并行加速",
    summary:
      "复杂任务智能拆解，多个 Sub Agent 同时执行，等待时间从串行变为并行。",
    icon: Bot,
    steps: [
      "Host Agent 分析并拆解任务",
      "多个 Sub Agent 并行推进子任务",
      "右侧边栏实时追踪所有执行流",
    ],
    outcome: "适合复杂分析、批量处理、多步骤任务并行加速的场景。",
  },
  {
    title: "本地分析与复盘闭环",
    summary:
      "围绕当前工作区直接执行代码、查看记录、沉淀产物，把分析主链路做深做透。",
    icon: ShieldCheck,
    steps: [
      "在当前工作区持续推进行对话与分析",
      "使用本地执行链路完成代码和 SQL 操作",
      "保留执行记录、文件和工作区产物",
    ],
    outcome: "适合当前阶段以单机个人模式稳定完成分析与复盘任务。",
  },
  {
    title: "工业数据分析与复盘",
    summary:
      "从上传数据、执行 Python / SQL，到保留中间文件与最终结论，形成完整分析闭环。",
    icon: Database,
    steps: [
      "上传 CSV / Excel / 连接 PostgreSQL",
      "在会话中执行分析、SQL 查询与代码",
      "保留工作区文件与上下文",
    ],
    outcome: "适合报表分析、异常复盘、结构化问题排查。",
  },
  {
    title: "知识检索与关系探索",
    summary:
      "在分析工作台内管理知识库、检索文档，再到知识图谱探索，形成连续的知识工作流。",
    icon: ScanSearch,
    steps: [
      "分析页面内打开知识库管理",
      "上传文档、RAG 查询与检索",
      "GraphRAG 关系浏览与问答",
    ],
    outcome: "适合知识沉淀、文档理解和关系脉络探索，无需切换页面。",
  },
  {
    title: "工具协同型任务",
    summary:
      "当任务需要外部工具、环境约束和人工确认时，艾斯提供的是一套作业面，而非聊天外壳。",
    icon: Blocks,
    steps: [
      "确认任务能力与资源配置",
      "通过连接器 / 技能调用外部能力",
      "通过 AskUser 处理关键确认点",
    ],
    outcome: "适合需要控制、留痕和协作边界的复杂任务。",
  },
  {
    title: "技能扩展与场景定制",
    summary:
      "在分析页面内打开技能市场，安装后立即在会话中使用，无缝扩展 AI 能力边界。",
    icon: Library,
    steps: [
      "在分析页面打开技能市场弹窗",
      "浏览和安装适合的技能",
      "安装即刻在当前会话中使用",
    ],
    outcome: "适合有标准化流程的专业领域场景，无需切换页面。",
  },
];

export const workflowSteps: WorkflowStep[] = [
  {
    title: "输入任务与资料",
    detail: "把目标、原始数据、文档和上下文拉进当前任务，而非零散粘贴。",
    icon: FileStack,
  },
  {
    title: "任务分解与规划",
    detail: "复杂任务自动拆分为子任务，分配给 Sub Agent 并行执行，实时追踪进度。",
    icon: Bot,
  },
  {
    title: "Agent 执行与协同",
    detail: "流式执行、工具调用、人工确认——形成可持续推进的作业链，右侧边栏实时可视化。",
    icon: BrainCircuit,
  },
  {
    title: "结果沉淀为资产",
    detail: "对话、代码、图表、结论全部归入工作区，随时继续复盘或交接。",
    icon: GitBranch,
  },
  {
    title: "导出与复核",
    detail: "关键结果、文件和边界整理成可复核材料，交付的不只是一段对话。",
    icon: ShieldCheck,
  },
];

export const trustCards: TrustCard[] = [
  {
    title: "后续规划",
    tone: "planned",
    summary: "以下功能已进入路线图，进展公开透明。",
    items: [
      "技能社区共享市场",
      "多模态能力扩展",
      "企业级审计与合规",
    ],
  },
];

export const entryCards: EntryCard[] = [
  {
    title: "开始分析",
    description: "进入主分析链路，围绕当前任务展开会话、执行与沉淀。",
    action: "进入 /workspace",
    onClick: () => goToWorkspace(),
  },
  {
    title: "知识库",
    description: "在分析工作台中打开知识库，管理文档、智能检索。",
    action: "在 /workspace 中使用",
    onClick: () => goToWorkspace(),
  },
  {
    title: "知识图谱",
    description: "在分析工作台内打开图谱，探索 GraphRAG 实体关系与知识脉络。",
    action: "打开 /workspace?overlay=knowledge_graph",
    onClick: () => goToWorkspace("knowledge_graph"),
  },
  {
    title: "技能市场",
    description: "在分析工作台中浏览技能市场，安装技能并立即使用。",
    action: "在 /workspace 中使用",
    onClick: () => goToWorkspace(),
  },
];
