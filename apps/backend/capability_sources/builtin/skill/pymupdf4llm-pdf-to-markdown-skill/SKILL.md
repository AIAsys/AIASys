+++
name = "pymupdf4llm PDF 转 Markdown"
description = "将 PDF 文件转换为 Markdown，供 AI Agent 阅读。适用于需要\n阅读论文、文档或任何 PDF 内容并提取文本进行分析的任务。\n涵盖 pymupdf4llm 转换、图表处理以及批量处理。\n设计为自主研究工作流中论文下载与 Agent 阅读之间的桥梁。"
+++


# PDF 转 Markdown

将 PDF 文件转换为 Markdown，以便 Agent 阅读和分析。

## 何时使用此 skill

- 下载的 arxiv 论文需要由 Agent 阅读
- 任何需要提取文本进行分析的 PDF 文档
- 从 PDF 集合构建可读的知识库
- 为自主研究的"文献分析"阶段准备论文

## 何时不使用

- PDF 是没有 OCR 层的扫描图像（需要先用 OCR 工具处理）
- 只需要元数据（标题、摘要）—— arxiv API 可直接提供
- 文件已经是文本/Markdown 格式

## 核心规则

### 规则 1：以 pymupdf4llm 作为主要工具

`pymupdf4llm` 可生成最高质量的 Markdown 输出，保留文档结构、
表格和图片引用。

```bash
pip install pymupdf4llm
python -m pymupdf4llm input.pdf output.md
```

### 规则 2：验证输出

转换后，检查：
- 输出文件非空，大小合理（典型论文大于 1KB）
- 章节标题被保留（查找 `#`、`##` 标记）
- 表格以 Markdown 表格形式出现或已被提取
- 输出中没有原始二进制乱码

### 规则 3：优雅处理失败

如果 pymupdf4llm 失败（PDF 损坏、加密等），尝试降级方案：

1. `pymupdf` (fitz) 纯文本提取：
   ```python
   import fitz
   doc = fitz.open("paper.pdf")
   text = "\n".join(page.get_text() for page in doc)
   with open("paper.md", "w") as f:
       f.write(text)
   ```

2. `pdftotext` (poppler-utils)：
   ```bash
   pdftotext -layout paper.pdf paper.md
   ```

### 规则 4：文件命名与组织

- 输入：`papers/{paper_id}.pdf`
- 输出：`papers/{paper_id}.md`
- 在文件名中保留论文 ID，以便追溯
- 不要覆盖原始 PDF

## 使用方法

### 单文件转换

```bash
python -m pymupdf4llm papers/2302.00411.pdf papers/2302.00411.md
```

### 批量转换

```bash
for pdf in papers/*.pdf; do
    md="${pdf%.pdf}.md"
    if [ ! -f "$md" ]; then
        echo "Converting: $pdf"
        python -m pymupdf4llm "$pdf" "$md"
    fi
done
```

### Python 脚本

```python
import pymupdf4llm
import pathlib

def convert_pdf_to_md(pdf_path: str, md_path: str | None = None) -> str:
    """将 PDF 文件转换为 Markdown。

    参数:
        pdf_path: 输入 PDF 文件的路径。
        md_path: 可选的输出路径。如果未提供，则将 .pdf 替换为 .md。

    返回:
        生成的 Markdown 文件的路径。
    """
    md_path = md_path or pdf_path.rsplit(".pdf", 1)[0] + ".md"
    pymupdf4llm.convert(
        pdf_path,
        output=md_path,
        write_images=False,  # 不将图片提取为单独的文件
    )
    return md_path
```

## 输出内容

pymupdf4llm 生成的 Markdown 包含：
- **标题**：`#`、`##`、`###` 结构，从文档布局中保留
- **段落**：自然的文本流，已去除连字符
- **表格**：检测到的地方以 Markdown 表格格式呈现
- **列表**：保留项目符号和编号列表
- **图片**：`![image](paper_id_001.png)` 引用，附带提取的图片
- **代码块**：等宽部分以围栏代码块呈现
- **数学公式**：检测到的地方保留 LaTeX 数学公式

## 为 Agent 内联阅读而转换

当 Agent 需要在有限的上下文窗口内阅读时：

```python
import pymupdf4llm

# 将全文作为单个字符串获取（不按页面拆分）
markdown_text = pymupdf4llm.to_markdown("paper.pdf")

# 如果论文较长，Agent 可以按章节阅读
print(f"论文长度: {len(markdown_text)} 字符")

# 仅提取摘要和引言
sections = markdown_text.split("\n# ")
abstract = next((s for s in sections if s.startswith("Abstract")), None)
intro = next((s for s in sections if "Introduction" in s), None)
```

## 与 arxiv-search 的常见工作流

```
1. [arxiv-search]  搜索并筛选论文
2. [arxiv-search]  下载 PDF → papers/{paper_id}.pdf
3. [pdf-to-markdown]  转换 PDF → papers/{paper_id}.md
4. [agent]  阅读 papers/{paper_id}.md 并提取洞察
5. [agent]  撰写文献分析笔记
```

## 交付检查清单

- [ ] 所有目标 PDF 转换成功（输出非空）
- [ ] 章节结构被保留（抽查标题级别）
- [ ] 输出文件命名与源 PDF 保持一致
- [ ] 失败的转换已记录原因
- [ ] Markdown 文件可读（无原始二进制内容，无过多空白）

---

*PDF 是展示格式。Markdown 是阅读格式。先转换，再阅读。*
