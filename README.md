# Financial Bad News

Automated pipeline for fetching, filtering, classifying, and aggregating negative financial news related to banking.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
```

Edit `.env` to provide `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` plus optional overrides.

## Usage

- Single fetch: `financial-bad-news fetch`
  - Override keyword: `--keyword 银行`
  - Custom negative keywords: `--keywords 漏洞,诈骗`
  - Adjust sentiment threshold: `--threshold 0.4`
  - Change page size: `--page-size 30`
  - Backfill recent history: `--min-timestamp 2024-01-01T00:00:00`
- Generate RSS: `financial-bad-news rss --output feed.xml`
- Start scheduler: `financial-bad-news scheduler`
- Launch UI: `financial-bad-news serve --host 0.0.0.0 --port 5000`
- Clear today’s data: `financial-bad-news clear-today`

### Web UI

- 调试面板可直接运行一次抓取并查看执行结果。
- 筛选面板支持按标题/描述关键词、匹配关键词、本地情感、LLM 判定筛选新闻。
- 列表支持分页浏览，可通过顶部下拉选择每页显示数量。
- 每条新闻卡片展示过滤理由、本地情感、LLM 判定与原文链接。

## Development

Execute the automated test suite with:

```bash
pytest
```
