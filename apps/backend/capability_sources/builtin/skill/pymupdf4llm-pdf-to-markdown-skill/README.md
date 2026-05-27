# PDF 转 Markdown

将 PDF 文件转换为 Markdown，供 AI Agent 阅读和分析。基于 pymupdf4llm 实现，支持图表处理和批量转换。

## 适用场景

- 下载的 arXiv 论文需要由 Agent 阅读
- 从 PDF 集合构建可读的知识库
- 任何需要提取文本进行分析的 PDF 文档
- 为自主研究的"文献分析"阶段准备论文

## 注意事项

- 扫描图像 PDF（无文本层）需要先用 OCR 工具处理
- 需要保留版式的复杂文档建议使用 `paddleocr-skill`
