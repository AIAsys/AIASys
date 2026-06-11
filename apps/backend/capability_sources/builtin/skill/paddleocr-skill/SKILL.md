+++
name = "PaddleOCR 文档提取"
description = "基于 PaddleOCR Layout Parsing API 将 PDF/图片转换为 Markdown，保留文档版式、表格和图片。\n当用户需要把扫描版 PDF、图片格式的文档或包含复杂版式的 PDF 转为可编辑文本时使用。\nAgent 会主动检查工作区是否已配置 PADDLEOCR token，缺失时询问用户提供；若用户不提供，回退到 pymupdf4llm。\n"

[[env_fields]]
name = "PADDLEOCR_API_URL"
required = true
description = "Layout Parsing API 地址"
default_value = "https://b6cdz14b8ch3q5z1.aistudio-app.com/layout-parsing"

[[env_fields]]
name = "PADDLEOCR_TOKEN"
required = true
description = "API 认证 token"
+++


# PaddleOCR 文档提取 Skill

将 PDF 文档或图片转换为结构化 Markdown，自动识别版式布局、表格、图表和图片。

## 何时使用

- 用户提供了扫描版 PDF 或图片，需要提取其中的文字内容
- PDF 包含复杂版式（多栏、表格、图文混排），普通文本提取会丢失结构
- 需要保留文档中的表格结构和图片位置信息
- 文档方向不端正（倾斜、倒置），需要自动校正

## 何时不使用

- 文档已经是可复制文本的 PDF，且版式简单 — 优先用 `pymupdf4llm-pdf-to-markdown-skill`，更快更轻
- 只需要纯文本，不需要保留版式 — 直接用 pymupdf4llm
- 没有 PaddleOCR API 访问权限 — 回退到 pymupdf4llm 或其他 OCR 方案

## 支持格式

- **PDF**：自动识别多页文档版式
- **图片**：PNG、JPG、JPEG、BMP、TIFF

## 配置

PaddleOCR 需要 API token 才能工作。Agent 使用本 skill 前按以下流程处理：

1. **检查**：调用 `GetEnvVar` 查看工作区是否已有 `PADDLEOCR_API_URL` 和 `PADDLEOCR_TOKEN`
2. **已有** → 直接执行提取
3. **缺失** → 询问用户是否提供：
   - 用户提供 → 用 `SetEnvVarTool` 写入工作区环境变量（存储在 `.workspace/workspace.json` 的 `runtime_binding.env_vars`）
   - **用户不提供 → 不再询问**，回退到 `pymupdf4llm-pdf-to-markdown-skill`

| 变量 | 必填 | 说明 |
|------|------|------|
| `PADDLEOCR_API_URL` | 是 | Layout Parsing API 地址 |
| `PADDLEOCR_TOKEN` | 是 | API 认证 token |

手动设置方式（Agent 可直接调用工具，无需手动执行）：

```bash
python3 skills/builtin/aiasys-platform-skill/scripts/env_vars.py set \
  --name PADDLEOCR_API_URL --value "https://your-paddleocr-endpoint/api"

python3 skills/builtin/aiasys-platform-skill/scripts/env_vars.py set \
  --name PADDLEOCR_TOKEN --value "your-api-token"
```

## 使用方式

```bash
# 提取 PDF（默认模式）
python3 skills/builtin/paddleocr-skill/scripts/extract.py \
  --file /workspace/document.pdf \
  --file_type 0 \
  --output_dir /workspace/extracted/

# 提取图片
python3 skills/builtin/paddleocr-skill/scripts/extract.py \
  --file /workspace/scan.png \
  --file_type 1 \
  --output_dir /workspace/extracted/

# 启用全部增强功能（方向校正 + 文档展平 + 图表识别）
python3 skills/builtin/paddleocr-skill/scripts/extract.py \
  --file /workspace/tilted_scan.pdf \
  --file_type 0 \
  --output_dir /workspace/extracted/ \
  --use_doc_orientation_classify \
  --use_doc_unwarping \
  --use_chart_recognition
```

## 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--file` | 路径 | 是 | 输入文件路径，支持相对路径或 `/workspace/...` 形式 |
| `--file_type` | int | 否 | 0=PDF（默认），1=图片 |
| `--output_dir` | 路径 | 否 | 输出目录，默认 `<文件名>_extracted/` |
| `--use_doc_orientation_classify` | flag | 否 | 启用文档方向分类，自动检测并校正倾斜/倒置 |
| `--use_doc_unwarping` | 否 | 否 | 启用文档展平，校正曲面扫描（如书籍弯曲） |
| `--use_chart_recognition` | flag | 否 | 启用图表识别，提取图表中的数据关系 |

### 参数选择建议

- **普通文档**：不加任何 flag，默认模式即可
- **扫描件倾斜/倒置**：加 `--use_doc_orientation_classify`
- **书籍/曲面扫描**：加 `--use_doc_unwarping`
- **含数据图表的报告**：加 `--use_chart_recognition`
- **可以同时启用多个 flag**，但处理时间会相应增加

## 输出

- `doc_{i}.md` — 提取的 Markdown 文档，保留原始版式结构
- `images/` — 文档中的图片保存到输出目录下的子目录

## 与 pymupdf4llm 的配合

```
用户上传 PDF
    ↓
判断 PDF 类型
    ├── 扫描版/图片版/复杂版式 → PaddleOCR
    └── 普通可复制文本 PDF → pymupdf4llm（更快）
    ↓
提取的 Markdown → 知识库上传 / 知识图谱摄入 / Agent 阅读
```

## 相关 Skills

- `pymupdf4llm-pdf-to-markdown-skill` — 普通 PDF 转 Markdown，不需要 API
- `pdf-translate-skill` — PDF 保版式翻译
