# PaddleOCR 文档提取

基于 PaddleOCR Layout Parsing API 将 PDF/图片转换为 Markdown，保留文档版式、表格和图片。

## 适用场景

- 扫描版 PDF 或图片格式文档的文字提取
- 复杂版式 PDF 的结构化转换
- 需要保留表格、图表位置的文档处理

## 环境变量配置

| 变量 | 必填 | 说明 | 默认值 |
|------|------|------|--------|
| `PADDLEOCR_API_URL` | 是 | Layout Parsing API 地址 | `https://b6cdz14b8ch3q5z1.aistudio-app.com/layout-parsing` |
| `PADDLEOCR_TOKEN` | 是 | API 认证 token | - |

## 注意事项

- 若未配置 token，Agent 会主动询问用户
- 用户不提供 token 时，回退到 `pymupdf4llm-pdf-to-markdown-skill`
