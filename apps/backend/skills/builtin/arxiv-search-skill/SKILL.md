+++
name = "arxiv 论文搜索与下载"
description = "在 arxiv.org 上搜索并下载学术论文。当任务需要查找相关论文、\n进行文献综述或下载 PDF 以供分析时使用。涵盖 arxiv API 搜索、\n论文元数据获取、PDF 下载以及带速率限制保护的批量处理。\n专为自主研究工作流设计，让 Agent 能够自行检索文献。"
+++


# arxiv 论文搜索与下载

通过官方 API 在 [arxiv.org](https://arxiv.org) 上搜索并下载论文。

## 何时使用此 skill

- 用户要求"查找关于 X 的论文"、"在 arxiv 上搜索 Y"或"做文献综述"
- 自主研究 Agent 需要在诊断/改进前收集参考文献
- 需要下载特定论文的 PDF 进行阅读或分析
- 基于最新出版物构建知识库

## 何时不应使用

- 通用网页搜索 — 改用 WebSearch/WebFetch
- 付费墙后的论文或来自其他平台的论文（使用对应平台的 API）
- 在已下载论文中进行全文搜索 — 此 skill 仅覆盖搜索+下载

## 核心规则

### 规则 1：使用 arxiv API，不要爬取

arxiv 官方 API 端点为：

```
https://export.arxiv.org/api/query
```

永远不要爬取 `arxiv.org` 的 HTML 页面。API 返回结构化的 Atom XML，是唯一支持的访问方式。

### 规则 2：遵守速率限制

arxiv 对 API 调用施加速率限制。规则如下：

- 连续 API 调用之间至少间隔 3 秒
- 批量下载时，每次 PDF 下载之间间隔 1 秒
- 使用 `User-Agent` 请求头标明你的工具（例如 `AIASys/1.0`）
- 如果收到 503 响应，等待 30 秒后重试

### 规则 3：谨慎搜索

- arxiv 搜索在内部使用 Lucene 查询语法
- **重要**：默认情况下空格被视为 OR。使用 `+` 或 `AND` 表示必须同时包含的词语
- 示例：`electricity+price+forecasting` 匹配全部三个词；`electricity price forecasting` 匹配任意一个
- 支持字段限定搜索：`ti:`、`au:`、`abs:`、`cat:`
- `sortBy` 可以是 `relevance`、`lastUpdatedDate` 或 `submittedDate`
- `sortOrder` 可以是 `ascending` 或 `descending`

### 规则 4：了解返回内容

API 返回 Atom XML，每条记录包含以下关键字段：

| 字段 | 含义 |
|------|------|
| `<id>` | 论文 URL（例如 `http://arxiv.org/abs/2302.00411`） |
| `<title>` | 论文标题 |
| `<summary>` | 摘要 |
| `<published>` | 发表日期 |
| `<updated>` | 最后更新日期 |
| `<author>` | 作者（每个标签一位） |
| `<arxiv:comment>` | 作者注释（页数、会议信息） |
| `<arxiv:journal_ref>` | 期刊引用（如已发表） |
| `<link title="pdf">` | PDF 下载链接 |
| `<arxiv:doi>` | DOI（如已分配） |
| `<category term="...">` | 主题分类（例如 `cs.AI`） |

### 规则 5：PDF 下载

PDF URL 模式：`https://arxiv.org/pdf/{paper_id}.pdf`

`paper_id` 从 `<id>` 字段中提取。示例：

- `<id>http://arxiv.org/abs/2302.00411v2</id>` → `paper_id` = `2302.00411` → PDF 地址为 `https://arxiv.org/pdf/2302.00411.pdf`

构造 PDF URL 前需去掉版本后缀（`v1`、`v2` 等）。

## API 用法

### 搜索论文

```bash
curl -s -H "User-Agent: AIASys/1.0" \
  "https://export.arxiv.org/api/query?search_query=all:reinforcement+learning&start=0&max_results=5&sortBy=relevance&sortOrder=descending"
```

Python 等价代码：
```python
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

def search_arxiv(query: str, max_results: int = 10, start: int = 0):
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({
        "search_query": f"all:{query}",
        "start": start,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    req = urllib.request.Request(url, headers={"User-Agent": "AIASys/1.0"})
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode()
```

### 获取单篇论文元数据

```bash
curl -s -H "User-Agent: AIASys/1.0" \
  "https://export.arxiv.org/api/query?id_list=2302.00411"
```

### 下载 PDF

```bash
curl -s -L -H "User-Agent: AIASys/1.0" \
  "https://arxiv.org/pdf/2302.00411.pdf" -o paper.pdf
```

### 字段限定搜索

**所有支持的字段前缀**（来自 arxiv 官方 API 文档）：

| 前缀 | 搜索范围 | 示例使用场景 |
|------|----------|-------------|
| `ti:` | 标题 | `ti:transformer+attention` |
| `au:` | 作者 | `au:bengio` — 查找某位作者的论文 |
| `abs:` | 摘要 | `abs:probabilistic+forecasting` |
| `cat:` | 主题分类 | `cat:cs.AI` — 限定领域 |
| `jr:` | 期刊引用 | `jr:Nature` — 查找已发表版本 |
| `co:` | 注释 | `co:accepted` — 搜索接收备注 |
| `rn:` | 报告编号 | 机构报告编号 |
| `all:` | 以上所有字段 | 默认的广泛搜索 |
| `id:` | 论文 ID | **避免使用** — 改用 `id_list` 参数 |

> `id:` 前缀虽然存在，但不应与 `search_query` 一起使用；使用 `id_list` 参数来正确处理文章版本。

```
# 按标题搜索
search_query=ti:transformer+attention

# 按摘要搜索
search_query=abs:energy+AND+abs:price+AND+abs:forecasting

# 按分类搜索（cs.AI = 人工智能，stat.ML = 机器学习）
search_query=cat:cs.AI+AND+all:autonomous+agent

# 组合搜索
search_query=ti:diffusion+AND+cat:cs.LG

# 搜索注释字段（被会议接收的论文）
search_query=co:accepted+AND+all:deep+learning

# 搜索期刊引用（已发表版本）
search_query=jr:J.+Mach.+Learn.+Res.+AND+all:attention
```

### 日期过滤

arxiv API 文档中记录了 `submittedDate` 过滤器的格式为 `[YYYYMMDDTTTT+TO+YYYYMMDDTTTT]`（24 小时 GMT）。**然而，该过滤器在实际使用中不可靠** — 使用官方文档中的精确格式进行测试时，始终返回零结果。

**推荐的按日期过滤替代方案：**

1. **按提交日期排序**并在客户端过滤：
   ```
   sortBy=submittedDate&sortOrder=descending
   ```
   然后解析响应中的 `<published>` 字段，仅保留日期范围内的论文。

2. **按最后更新日期排序**以查找最新修订：
   ```
   sortBy=lastUpdatedDate&sortOrder=descending
   ```

3. **结合分类 + 关键词**来缩小"时代"范围（例如，较新的方法通常有更新的术语）：
   ```
   search_query=cat:cs.LG+AND+all:transformer+AND+all:attention
   ```

### 括号与复杂分组

对于复杂的布尔表达式，使用 `%28` 代替 `(`，`%29` 代替 `)`：

```
# (LSTM OR Transformer) AND electricity AND NOT wind
search_query=%28all:lstm+OR+all:transformer%29+AND+all:electricity+ANDNOT+all:wind

# 作者 X，标题不是 (Y OR Z)
search_query=au:hinton+ANDNOT+%28ti:deep+OR+ti:learning%29
```

> 已验证：括号分组在 arxiv 的 Lucene 查询解析器中有效。

### 结果数量限制

API **对总结果数设有限制**（通常约可检索 2,000 条）。对于返回超过 1,000 条结果的查询：
- 优化查询使其更具体
- 使用字段限定前缀（`ti:` 对比 `all:`）来缩小范围
- 添加日期范围过滤器
- 对于批量元数据获取，改用 [OAI-PMH](https://info.arxiv.org/help/oa/index.html) 接口

### API 与 HTML 搜索行为对比

arxiv **HTML 搜索**界面默认按提交日期降序排序。**API** 默认按相关性排序。两者之间的结果看起来会不同。调试搜索查询时，直接在浏览器中使用 API（而非 HTML 搜索）来验证你的程序将收到的内容。

## 搜索技巧

### 布尔运算符

arxiv API 支持标准 Lucene 布尔运算符。**仅空格被视为 OR** — 始终使用显式运算符以获得精确性。

| 运算符 | 含义 | 示例 |
|--------|------|------|
| `+`（或带 AND 时省略） | 必需词语 | `all:energy+forecasting` |
| `AND` | 两个词语都必需 | `all:energy+AND+all:price` |
| `OR` | 任一词语（裸空格的默认值） | `all:lstm+OR+all:transformer` |
| `ANDNOT` | 排除词语 | `all:forecasting+ANDNOT+all:wind` |

**关键规则**：在 URL 查询字符串中，使用 `+` 表示词语内部的空格（例如 `reinforcement+learning`），使用 `+AND+`、`+OR+`、`+ANDNOT+` 表示布尔运算符。

### 使用括号分组

组合条件以构建复杂查询：

```
# (LSTM OR Transformer) AND electricity AND forecasting
search_query=(all:lstm+OR+all:transformer)+AND+all:electricity+AND+all:forecasting

# (deep learning) AND (price OR load) AND NOT wind
search_query=all:deep+learning+AND+(all:price+OR+all:load)+ANDNOT+all:wind
```

### 精确短语匹配

使用双引号进行精确的多词短语匹配：

```
search_query=all:%22reinforcement+learning%22
```
（`%22` 是 URL 编码后的 `"`）

在 curl 中使用 `--data-urlencode` 更简洁：
```bash
curl -s -H "User-Agent: AIASys/1.0" \
  -G "https://export.arxiv.org/api/query" \
  --data-urlencode 'search_query=all:"energy price forecasting"' \
  --data-urlencode 'max_results=5'
```

### 作者搜索

```
# 查找某位特定作者的论文
search_query=au:bengio

# 作者 + 主题
search_query=au:hinton+AND+all:deep+learning

# 多位作者（任意一位）
search_query=au:goodfellow+OR+au:bengio
```

注意：在 arxiv 的索引中，作者姓名格式为 `lastname_firstname` 或仅 `lastname`，因此应使用 `au:bengio` 而非 `au:yoshua+bengio`。

### 分类过滤

分类是缩小范围的有力方式。每篇论文有一个主要分类和可选的交叉分类。

```
# 单一分类
search_query=cat:cs.AI

# 多个分类（任意匹配）
search_query=cat:cs.AI+OR+cat:cs.LG

# 跨分类主题搜索
search_query=cat:stat.ML+AND+all:probabilistic+forecasting

# 排除某个分类
search_query=all:reinforcement+learning+ANDNOT+cat:cs.RO
```

### 按论文 ID 搜索

```
# 单篇论文（例如，用于确认是否为正确的一篇）
search_query=id:2302.00411

# 多篇特定论文
id_list=2302.00411,2305.00362,2412.07075
```

`id_list` 参数绕过搜索引擎，直接获取指定论文 — 快速且精确。

### 多字段定向搜索

同时用不同词语搜索不同字段：

```
# 标题包含 "transformer"，摘要提到 "attention mechanism"
search_query=ti:transformer+AND+abs:attention+mechanism

# 作者 "vaswani" 且论文关于 "attention"
search_query=au:vaswani+AND+all:attention
```

### 结果调优策略

| 情况 | 操作 |
|------|------|
| 结果太多（> 100） | 添加 `AND` 词语，限定到 `ti:` 或 `abs:`，按 `cat:` 过滤 |
| 结果太少 | 从 `ti:` 切换到 `all:`，用 `OR` 连接同义词，移除分类过滤器 |
| 需要最新工作 | `sortBy=submittedDate&sortOrder=descending` |
| 需要开创性工作 | `sortBy=relevance&sortOrder=descending` — 较早的有影响力的论文排名更高 |
| 查找综述论文 | 添加 `all:survey+OR+all:review+OR+all:comprehensive` |
| 查找代码/实践工作 | 添加 `all:benchmark+OR+all:open+source+OR+all:implementation` |

### 基于日期的过滤

API 本身不支持日期范围，但可以近似实现：

```
# 最新论文（最后更新）
sortBy=lastUpdatedDate&sortOrder=descending

# 结合分类获取某领域的最新论文
search_query=cat:cs.LG+AND+all:diffusion+model&sortBy=submittedDate&sortOrder=descending
```

如需更精确的日期过滤，使用 `start` 参数分页浏览近期结果，并按 `<published>` 日期在代码中过滤。

### 迭代优化模式

自主研究的最有效方法：

```
第一轮：广泛调研
  → all:energy+AND+all:price+AND+all:forecasting  (max_results=20)

第二轮：分析结果，优化
  → ti:probabilistic+AND+abs:electricity+market  (max_results=10)

第三轮：锁定关键作者或跟踪引用链
  → au:ziel+AND+all:probabilistic+forecasting  (max_results=5)

第四轮：获取确切需要的论文
  → id_list=2302.00411,2305.00362,2412.07075
```

### 常见搜索配方

```bash
# "查找时间序列预测领域的最新深度学习论文"
search_query=cat:cs.LG+AND+ti:time+series+forecasting&sortBy=submittedDate&sortOrder=descending

# "概率电价预测有什么新进展？"
search_query=abs:probabilistic+AND+abs:electricity+AND+abs:price&sortBy=lastUpdatedDate&sortOrder=descending

# "查找关于储能优化的综述/调研论文"
search_query=all:energy+storage+optimization+AND+(all:survey+OR+all:review)&sortBy=relevance&sortOrder=descending

# "查找某位已知作者在特定领域的论文"
search_query=au:hyndman+AND+all:probabilistic+forecasting

# "获取引用/使用某种特定方法的论文"
search_query=all:conformal+prediction+AND+all:energy+ANDNOT+cat:stat.TH
```

## 自主研究的常见搜索流程

当 Agent 需要为研究任务查找论文时，遵循以下流程：

1. **广泛扫描**：`search_query=all:{keywords}`，设置 `max_results=20`，`sortBy=relevance`
2. **按字段缩小范围**：添加字段限定符（`ti:`、`abs:`、`cat:`）以过滤噪声
3. **按时间排序**：使用 `sortBy=submittedDate&sortOrder=descending` 查找最新工作
4. **扫描摘要**：解析 `<summary>` 字段，筛选出 3-5 篇最相关的论文
5. **深度下载**：下载筛选出的论文的 PDF
6. **提取并保存**：使用 PDF 提取工具转换为 Markdown 供 Agent 阅读

## 解析 arxiv Atom XML

Python 最小解析器：

```python
import xml.etree.ElementTree as ET

ns = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

def parse_results(xml_str: str) -> list[dict]:
    root = ET.fromstring(xml_str)
    papers = []
    for entry in root.findall("atom:entry", ns):
        paper_id = entry.find("atom:id", ns).text.strip()
        # 从 URL 中提取 ID：http://arxiv.org/abs/2302.00411v2 -> 2302.00411
        arxiv_id = paper_id.split("/abs/")[-1].split("v")[0]
        papers.append({
            "id": arxiv_id,
            "title": entry.find("atom:title", ns).text.strip().replace("\n", " "),
            "summary": entry.find("atom:summary", ns).text.strip().replace("\n", " "),
            "published": entry.find("atom:published", ns).text.strip(),
            "updated": entry.find("atom:updated", ns).text.strip(),
            "authors": [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)],
            "comment": getattr(entry.find("arxiv:comment", ns), "text", ""),
            "journal_ref": getattr(entry.find("arxiv:journal_ref", ns), "text", ""),
            "doi": getattr(entry.find("arxiv:doi", ns), "text", ""),
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            "categories": [c.get("term") for c in entry.findall("atom:category", ns)],
        })
    return papers
```

## 下载论文供 Agent 分析

当目标是为了让 Agent 阅读和分析论文时：

1. 将 PDF 下载到本地目录（例如 `papers/` 或临时目录）
2. 使用 `pymupdf4llm` 或类似工具将 PDF 转换为 Markdown：
   ```bash
   pip install pymupdf4llm
   python -m pymupdf4llm paper.pdf paper.md
   ```
3. Agent 阅读 Markdown 文件以理解论文内容
4. 将提取的见解保存到结构化笔记中

## 常见主题分类

### 人工智能与机器学习
| 分类 | 领域 |
|------|------|
| Artificial Intelligence | `cs.AI` |
| Machine Learning | `cs.LG` |
| Computation & Language (NLP) | `cs.CL` |
| Computer Vision | `cs.CV` |
| Neural & Evolutionary Computing | `cs.NE` |

### 统计与数学
| 分类 | 领域 |
|------|------|
| Machine Learning (Statistics) | `stat.ML` |
| Applications (Statistics) | `stat.AP` |
| Methodology (Statistics) | `stat.ME` |
| Optimization & Control | `math.OC` |
| Probability | `math.PR` |

### 能源与系统
| 分类 | 领域 |
|------|------|
| Systems & Control | `eess.SY` |
| Signal Processing | `eess.SP` |
| Energy (Physics) | `physics.app-ph` |

### 经济与金融
| 分类 | 领域 |
|------|------|
| Econometrics | `econ.EM` |
| General Economics | `econ.GN` |
| Quantitative Finance | `q-fin` |
| Mathematical Finance | `q-fin.MF` |
| Computational Finance | `q-fin.CP` |

### 其他实用分类
| 分类 | 领域 |
|------|------|
| Computational Engineering | `cs.CE` |
| Multiagent Systems | `cs.MA` |
| Robotics | `cs.RO` |
| Software Engineering | `cs.SE` |
| Databases | `cs.DB` |

## 批量论文收集工作流

用于自主文献综述：

```
1. search_arxiv("keyword set A", max_results=20)
2. sleep 3 seconds
3. search_arxiv("keyword set B", max_results=20)
4. 解析结果，按 paper_id 去重
5. 对每篇 shortlisted 论文：
   a. curl PDF → papers/{paper_id}.pdf
   b. sleep 1 second
6. 对每个 PDF：
   a. python -m pymupdf4llm papers/{paper_id}.pdf papers/{paper_id}.md
7. Agent 阅读 papers/{paper_id}.md 并提取关键见解
```

## 交付检查清单

文献搜索会话结束后：

- [ ] 搜索结果已解析并去重
- [ ] 论文元数据（标题、作者、摘要、arxiv ID）已保存
- [ ] 下载的 PDF 位于已知目录中
- [ ] 遵守了速率限制（无 503 响应）
- [ ] 从论文中提取的见解已写入结构化笔记
- [ ] 论文列表包含 arxiv ID 以供追溯

---

*arxiv 是一项免费分发服务。请尊重它 — 限制调用速率、使用正确的 User-Agent 请求头，不要过度请求 API。*
