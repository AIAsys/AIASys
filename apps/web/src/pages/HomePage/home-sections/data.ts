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
import { goToAnalysis } from "../navigation";
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
    route: "/analysis",
    summary:
      "适合从一个具体任务开始，Host Agent 自动分解子任务，实时追踪执行流程和结果。",
    bullets: [
      "复杂任务自动分解为 Sub Agent 并行执行",
      "右侧边栏实时查看执行流和工具调用",
      "文件、结果与导出集中沉淀",
    ],
    kind: "analysis",
    actionLabel: "进入分析工作台",
    onClick: () => goToAnalysis("knowledge_base"),
  },
  {
    title: "知识库",
    route: "/analysis?overlay=knowledge_base",
    summary:
      "在分析工作台内直接打开知识库弹窗，管理文档、执行检索，并把可用资源挂载回任务工作区。",
    bullets: [
      "分析页内直接打开知识库弹窗",
      "工作区只消费已挂载知识库",
      "知识库与图谱都以内嵌弹窗承接",
    ],
    kind: "knowledge",
    actionLabel: "在分析中打开",
    onClick: () => goToAnalysis("knowledge_base"),
  },
  {
    title: "知识图谱探索",
    route: "/analysis?overlay=knowledge_graph",
    summary:
      "适合在分析工作台里继续往下看，把零散信息连成关系脉络，帮助你更快抓到重点。",
    bullets: [
      "从关系视角理解信息",
      "GraphRAG 实体关系浏览",
      "以内嵌图谱弹窗继续展开脉络",
    ],
    kind: "graph",
    actionLabel: "在分析中探索",
    onClick: () => goToAnalysis("knowledge_graph"),
  },
  {
    title: "技能市场",
    route: "/analysis",
    summary:
      "在分析工作台中直接打开技能市场，安装技能并立即在会话中使用。",
    bullets: [
      "分析页面内打开技能市场弹窗",
      "安装技能即刻可用",
      "自定义开发专属技能",
    ],
    kind: "skills",
    actionLabel: "在分析中使用",
    onClick: () => goToAnalysis(),
  },
];

export const capabilityCards: CapabilityCard[] = [
  {
    title: "多 Agent 并行执行",
    summary:
      "Host Agent 智能分解复杂任务，多个 Sub Agent 并行执行，大幅缩短任务完成时间。",
    icon: Bot,
    accent: "from-slate-950 via-indigo-800 to-violet-600",
    glow: "bg-foreground/10",
    features: [
      { label: "Host + 多 Sub Agent 并行架构", status: "已可用", tone: "ready" },
      { label: "任务自动分解与并行调度", status: "已可用", tone: "ready" },
      { label: "右侧执行流实时可视化", status: "已可用", tone: "ready" },
    ],
    note: "核心价值不是'单轮回答'，而是多 Agent 并行加速的任务执行闭环。",
  },
  {
    title: "会话化分析",
    summary:
      "围绕真实任务组织多轮对话、SSE 流式执行和人工确认，不把复杂分析压扁成一次性问答。",
    icon: BrainCircuit,
    accent: "from-slate-950 via-slate-800 to-slate-600",
    glow: "bg-foreground/10",
    features: [
      { label: "SSE 流式执行与实时响应", status: "已可用", tone: "ready" },
      { label: "会话历史续聊与状态恢复", status: "已可用", tone: "ready" },
      { label: "AskUser 人机协同确认", status: "已可用", tone: "ready" },
    ],
    note: "核心价值不是'会回答'，而是能围绕任务上下文持续推进。",
  },
  {
    title: "能力与工具接入",
    summary:
      "把连接器、技能与知识能力接入到同一工作面，工具调用可观测、可追溯。",
    icon: Wrench,
    accent: "from-slate-950 via-lime-900 to-emerald-700",
    glow: "bg-success/10",
    features: [
      { label: "连接器工具动态接入", status: "已可用", tone: "ready" },
      { label: "技能运行时调用", status: "已可用", tone: "ready" },
      { label: "工具调用详情追踪", status: "已可用", tone: "ready" },
    ],
    note: "关键不是'能不能接'，而是能否纳入会话执行闭环并被治理。",
  },
  {
    title: "工作区与资产沉淀",
    summary:
      "对话中产生的数据、文件和中间结果沉淀进工作区，让复盘与交接具备真实载体。",
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
      "当前版本默认使用本地执行链路，把体验集中在任务工作区、对话和执行证据上。",
    icon: ShieldCheck,
    accent: "from-slate-950 via-cyan-900 to-blue-700",
    glow: "bg-info/10",
    features: [
      { label: "本地 Python / IPython 执行链路", status: "已可用", tone: "ready" },
      { label: "任务内执行记录追踪", status: "已可用", tone: "ready" },
      { label: "默认本地执行路径", status: "已可用", tone: "ready" },
    ],
    note: "重点不是提供多种运行后端，而是把当前主线做稳、做清楚、做顺手。",
  },
  {
    title: "知识能力栈",
    summary:
      "在分析工作台内直接管理知识库、检索文档和探索知识图谱，无缝衔接分析流程。",
    icon: Network,
    accent: "from-slate-950 via-sky-900 to-cyan-700",
    glow: "bg-info/10",
    features: [
      { label: "分析页面内管理知识库", status: "已可用", tone: "ready" },
      { label: "GraphRAG 知识图谱探索", status: "已可用", tone: "ready" },
      { label: "统一文档提取与向量化", status: "已可用", tone: "ready" },
    ],
    note: "知识库与知识图谱使用独立路由页承接，任务工作区负责挂载、切换和回到执行上下文。",
  },
  {
    title: "数据库浏览器",
    summary:
      "直接在会话中连接 PostgreSQL 等数据库，查看表结构、执行 SQL 查询并沉淀结果。",
    icon: Database,
    accent: "from-slate-950 via-violet-900 to-purple-700",
    glow: "bg-info/10",
    features: [
      { label: "PostgreSQL 连接与表结构查看", status: "已可用", tone: "ready" },
      { label: "SQL 查询执行与结果展示", status: "已可用", tone: "ready" },
      { label: "MySQL/SQLite 多数据库支持", status: "已可用", tone: "ready" },
    ],
    note: "把数据查询和分析流程整合进同一工作台，无需切换工具。",
  },
  {
    title: "技能市场",
    summary:
      "在分析工作台内直接打开技能市场，安装和管理技能，无需跳转页面。",
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
      "把过程、结果和边界都讲清楚，避免只剩一张截图或一段不可追溯的最终回答。",
    icon: FileArchive,
    accent: "from-slate-950 via-amber-900 to-orange-700",
    glow: "bg-warning/10",
    features: [
      { label: "对话记录导出", status: "已可用", tone: "ready" },
      { label: "工作区导出与留痕", status: "已可用", tone: "ready" },
      { label: "Markdown/DOCX/PDF 多格式导出", status: "已可用", tone: "ready" },
    ],
    note: "价值不只在'得到结果'，更在'结果是否可复核、可交接、可沉淀'。",
  },
];

export const scenarioCards: ScenarioCard[] = [
  {
    title: "多 Agent 并行加速",
    summary:
      "复杂任务智能分解为多个子任务，由 Sub Agent 并行执行，大幅缩短完成时间。",
    icon: Bot,
    steps: [
      "Host Agent 智能分析并分解任务",
      "多个 Sub Agent 并行执行子任务",
      "右侧边栏实时查看所有执行流",
    ],
    outcome: "适合复杂分析、批量处理、多步骤任务并行加速的场景。",
  },
  {
    title: "本地分析与复盘闭环",
    summary:
      "围绕当前工作区直接执行代码、查看执行记录、沉淀产物，把主链路先做稳定。",
    icon: ShieldCheck,
    steps: [
      "在当前工作区继续推进对话与分析",
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
      "当任务需要外部工具、环境约束和人工确认时，艾斯更像一套作业面，而不是聊天外壳。",
    icon: Blocks,
    steps: [
      "确认任务能力与资源配置",
      "通过连接器 / 技能调外部能力",
      "通过 AskUser 处理关键确认点",
    ],
    outcome: "适合需要控制、留痕和协作边界的复杂任务。",
  },
  {
    title: "技能扩展与场景定制",
    summary:
      "在分析页面内打开技能市场，安装技能后立即在会话中使用，无缝扩展 AI 能力。",
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
    detail: "把目标、原始数据、文档和上下文拉进当前任务，而不是零散粘贴。",
    icon: FileStack,
  },
  {
    title: "任务分解与规划",
    detail: "复杂任务自动拆分为子任务，分配给 Sub Agent 并行执行，实时追踪进度。",
    icon: Bot,
  },
  {
    title: "Agent 执行与协同",
    detail: "通过流式执行、工具调用和 AskUser 形成可推进的作业链，右侧边栏实时可视化。",
    icon: BrainCircuit,
  },
  {
    title: "结果沉淀为资产",
    detail: "把对话、工作区文件和知识结果沉淀下来，便于继续复盘和交接。",
    icon: GitBranch,
  },
  {
    title: "导出与复核",
    detail: "把关键结果、文件和边界整理成可复核材料，而不是只留下聊天截图。",
    icon: ShieldCheck,
  },
];

export const trustCards: TrustCard[] = [
  {
    title: "后续规划",
    tone: "planned",
    summary: "以上功能已进入路线图，进展公开透明。",
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
    description: "进入主分析链路，围绕当前任务展开会话、执行和工作区沉淀。",
    action: "进入 /analysis",
    onClick: () => goToAnalysis(),
  },
  {
    title: "知识库",
    description: "在分析工作台中打开知识库弹窗，管理文档、智能检索。",
    action: "在 /analysis 中使用",
    onClick: () => goToAnalysis(),
  },
  {
    title: "知识图谱",
    description: "在分析工作台内打开知识图谱弹窗，探索 GraphRAG 实体关系和知识脉络。",
    action: "打开 /analysis?overlay=knowledge_graph",
    onClick: () => goToAnalysis("knowledge_graph"),
  },
  {
    title: "技能市场",
    description: "在分析工作台中打开技能市场，安装技能并立即使用。",
    action: "在 /analysis 中使用",
    onClick: () => goToAnalysis(),
  },
];
