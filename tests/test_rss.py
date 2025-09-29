from datetime import datetime

from financial_bad_news.pipeline import run_pipeline
from financial_bad_news.rss import generate_rss


def test_generate_rss_contains_items(monkeypatch):
    payload = {
        "data": {
            "items": [
                {
                    "title": "银行人脸识别漏洞",
                    "description": "可能导致盗刷",
                    "url": "https://example.com/rss",
                    "time": 1700000000,
                }
            ],
            "totalpage": 1,
        }
    }

    monkeypatch.setattr(
        "financial_bad_news.pipeline.TophubClient.search",
        lambda self, keyword, page=1, size=50: payload,
        raising=False,
    )
    monkeypatch.setattr(
        "financial_bad_news.pipeline.LocalClassifier.classify",
        lambda self, text: (0.1, True),
        raising=False,
    )
    monkeypatch.setattr(
        "financial_bad_news.pipeline.LLMClassifier.classify",
        lambda self, text: ("negative", 0.95),
        raising=False,
    )

    run_pipeline(min_timestamp=datetime(2023, 1, 1))
    rss_data = generate_rss(limit=10)
    rss_text = rss_data.decode("utf-8")
    assert "<item>" in rss_text
    assert "银行人脸识别漏洞" in rss_text
    assert "匹配关键词" in rss_text
    assert "LLM 判定" in rss_text
