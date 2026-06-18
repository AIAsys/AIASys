# PDF2ZH 翻译

基于 pdf2zh 提供当前工作区 PDF 的保版式翻译，输出单语和双语两份 PDF。

## 适用场景

- 将英文/外文 PDF 翻译为中文
- 需要保留 PDF 原始版式（图表位置、段落布局）
- 需要同时获得单语版和双语对照版

## 翻译服务

支持三种翻译服务：
- **google** — 免费，无需配置
- **openai** — 需要配置 OpenAI API key
- **gemini** — 需要配置 Google API key

## 特性

- 通过 `uvx` 隔离运行，不污染工作区 Python 环境
- 翻译进度实时输出，不黑屏等待
- 支持 `--pages` 参数按页码范围翻译，适合大文件试译
- 输出 translation_manifest.json 记录翻译元数据

## 注意事项

- 扫描件/图片 PDF 需先用 OCR 工具提取文字
- 纯文本翻译无需保留版式时，建议先用 `pymupdf4llm-pdf-to-markdown-skill` 转 Markdown
- 大文件（>50 页）建议先用 `--pages 1-5` 试译，确认效果后再全量翻译
