+++
name = "PDF2ZH 翻译"
description = "基于 pdf2zh 提供当前工作区 PDF 的保版式翻译能力，输出单语和双语两份 PDF。\n当用户需要将英文/外文 PDF 翻译为中文且保留原排版时使用。\n支持 google（免费）、openai、gemini 三种翻译服务。"
+++


# PDF2ZH 翻译 Skill

翻译当前会话工作区内的 PDF，保留原排版并输出 mono/dual 两份 PDF。

## 何时使用此 skill

- 用户说"翻译这个 PDF"、"把论文翻译成中文"
- 需要保留 PDF 原始版式（图表位置、段落布局）的翻译
- 需要同时获得单语版和双语对照版

## 何时不应使用

- PDF 是扫描件/图片（无文本层）— 先用 OCR 工具提取文字
- 只需要纯文本翻译，不需要保留版式 — 用 `pymupdf4llm-pdf-to-markdown-skill` 转 Markdown 后翻译
- 文件不是 PDF — 本 skill 只支持 PDF 输入
- 翻译非中文目标语言 — pdf2zh 主要面向中文输出，其他语言支持有限

## 核心规则

### 规则 1：确认 PDF 有文本层

如果 PDF 是扫描图片（例如旧论文扫描件），pdf2zh 无法识别文字，会直接复制原图。先用 `paddleocr-skill` 做 OCR 提取，或确认 PDF 可选中文字。

### 规则 2：优先使用 google 翻译器

google 翻译器免费、无需配置 API key，适合大多数场景。只有当：
- google 翻译质量不够（专业术语多）
- 需要特定文风或领域适配
才考虑 openai 或 gemini。

### 规则 3：大文件先试译

大文件（>50 页）首次翻译可能需要 5-15 分钟。建议先用 `--pages 1-5` 试译前几页，确认翻译效果和版式后再全量翻译。

### 规则 4：流式输出

翻译过程中 pdf2zh 的进度信息会实时透传到 stderr，方便观察翻译进度。不需要等待"黑屏"30 分钟。

## 使用方式

### 基本翻译（google，免费）

```bash
python3 skills/builtin/pdf-translate-skill/scripts/translate.py \
  --pdf_path /workspace/document.pdf \
  --source_lang en \
  --target_lang zh \
  --translator google
```

### 试译前几页（大文件推荐）

```bash
python3 skills/builtin/pdf-translate-skill/scripts/translate.py \
  --pdf_path /workspace/document.pdf \
  --pages 1-5
```

### 使用 OpenAI 翻译（质量更高，需配置 API key）

```bash
python3 skills/builtin/pdf-translate-skill/scripts/translate.py \
  --pdf_path /workspace/document.pdf \
  --translator openai
```

### 指定输出目录

```bash
python3 skills/builtin/pdf-translate-skill/scripts/translate.py \
  --pdf_path /workspace/document.pdf \
  --output_dir /workspace/translated/
```

### 忽略缓存重新翻译

```bash
python3 skills/builtin/pdf-translate-skill/scripts/translate.py \
  --pdf_path /workspace/document.pdf \
  --ignore_cache
```

## 参数说明

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--pdf_path` | 是 | — | PDF 文件路径（相对路径或 `/workspace/` 开头） |
| `--output_dir` | 否 | `pdf_translations/<文件名>/` | 输出目录 |
| `--source_lang` | 否 | `en` | 源语言代码 |
| `--target_lang` | 否 | `zh` | 目标语言代码 |
| `--translator` | 否 | `google` | 翻译服务：`google` / `openai` / `gemini` |
| `--pages` | 否 | 全部 | 只翻译指定页（如 `1-10`、`1,3,5`、`1-5,10`） |
| `--ignore_cache` | 否 | false | 忽略 pdf2zh 缓存，强制重新翻译 |

## 翻译服务配置

| 服务 | 费用 | 配置要求 | 适用场景 |
|------|------|----------|----------|
| `google` | 免费 | 无需配置 | 通用翻译，速度快 |
| `openai` | 按 token 计费 | 需 `OPENAI_API_KEY` 环境变量 | 专业术语、特定文风 |
| `gemini` | 按 token 计费 | 需 `GEMINI_API_KEY` 环境变量 | 长文档、Google 生态 |

环境变量在工作区级别通过 `aiasys-platform-skill` 配置：
```bash
python3 skills/builtin/aiasys-platform-skill/scripts/env_vars.py set --name OPENAI_API_KEY --value "sk-..."
```

## 输出

翻译完成后输出两份 PDF 和一个 manifest：

```
pdf_translations/document/
├── document-mono.pdf          # 单语翻译版（仅中文）
├── document-dual.pdf          # 双语对照版（原文在上，译文在下）
└── translation_manifest.json  # 元数据记录
```

manifest 包含：源文件路径、输出路径、使用的翻译器、语言对、页码范围等信息。

## 错误处理

| 问题 | 原因 | 解决 |
|------|------|------|
| "未找到 uvx 或 uv" | 运行环境缺少 uv | 先安装 uv：`curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| "pdf2zh 执行失败" | 网络问题或 PDF 损坏 | 检查网络，用 `--ignore_cache` 重试 |
| 输出是原图，没有翻译 | PDF 是扫描件，无文本层 | 先用 `paddleocr-skill` 做 OCR |
| 翻译超时 | 文件太大 | 用 `--pages` 分批翻译，或改用更快的翻译器（google） |
| 专业术语翻译不准 | google 对术语支持有限 | 改用 openai/gemini 并调整 prompt |

## 常见工作流

**论文翻译工作流：**
1. `arxiv-search-skill` 下载 PDF
2. `pymupdf4llm-pdf-to-markdown-skill` 转 Markdown 快速预览内容
3. 确认需要完整保留版式后，用本 skill 翻译
4. 得到 mono 版用于阅读，dual 版用于对照

**大文件渐进翻译工作流：**
1. 先用 `--pages 1-3` 试译，确认翻译效果
2. 满意后去掉 `--pages` 全量翻译，或分批 `--pages 1-20`、`--pages 21-40` 翻译
3. 全量翻译时加 `--ignore_cache` 确保一致性

## 相关 Skills

- `paddleocr-skill` — 扫描件 OCR 提取
- `pymupdf4llm-pdf-to-markdown-skill` — 无需保留版式时的纯文本提取
- `arxiv-search-skill` — 论文搜索与下载
