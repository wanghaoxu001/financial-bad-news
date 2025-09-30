from __future__ import annotations

from datetime import datetime, timezone

import pytest
import requests
from sqlalchemy import select

from financial_bad_news.db import session_scope
from financial_bad_news.models import NewsArticle
from financial_bad_news.pipeline import run_pipeline
from financial_bad_news.repository import delete_articles_since


@pytest.fixture
def mock_clients(monkeypatch):
    payload = {
        "data": {
            "items": [
                {
                    "title": "银行系统漏洞导致信用卡盗刷",
                    "description": "造成用户损失",
                    "url": "https://example.com/a",
                    "thumbnail": None,
                    "extra": "",
                    "time": int(datetime(2024, 1, 5).timestamp()),
                },
                {
                    "title": "普通新闻",
                    "description": "无关",
                    "url": "https://example.com/b",
                    "time": int(datetime(2023, 12, 1).timestamp()),
                },
            ],
            "totalpage": 1,
        }
    }

    def fake_search(self, keyword, page=1, size=50):  # noqa: D401
        return payload

    monkeypatch.setattr(
        "financial_bad_news.pipeline.TophubClient.search",
        fake_search,
        raising=False,
    )
    monkeypatch.setattr(
        "financial_bad_news.pipeline.LocalClassifier.classify",
        lambda self, text: (0.2, True),
        raising=False,
    )
    monkeypatch.setattr(
        "financial_bad_news.pipeline.LLMClassifier.classify",
        lambda self, text: ("negative", 0.9),
        raising=False,
    )


def test_run_pipeline_inserts_articles(mock_clients):
    stats = run_pipeline(min_timestamp=datetime(2023, 1, 1))
    assert stats["inserted"] == 1
    assert stats["processed"] == 1

    with session_scope() as session:
        articles = session.execute(select(NewsArticle)).scalars().all()
        assert len(articles) == 1
        article = articles[0]
        assert article.url == "https://example.com/a"
        assert article.local_is_negative is True
        assert article.llm_classification == "negative"
        assert article.reason is not None
        assert "关键词命中" in article.reason
        assert article.content_fingerprint is not None


def test_run_pipeline_skips_existing(mock_clients):
    run_pipeline(min_timestamp=datetime(2023, 1, 1))
    stats = run_pipeline(min_timestamp=datetime(2023, 1, 1))
    assert stats["inserted"] == 0
    assert stats["processed"] == 0


def test_run_pipeline_respects_today_cutoff(monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return cls(2024, 1, 6, 12, 0, 0)

    payload = {
        "data": {
            "items": [
                {
                    "title": "当日银行漏洞事件",
                    "description": "最新新闻",
                    "url": "https://example.com/new",
                    "time": int(datetime(2024, 1, 6, 6, 0, 0, tzinfo=timezone.utc).timestamp()),
                },
                {
                    "title": "前一天事件",
                    "description": "应被过滤",
                    "url": "https://example.com/old",
                    "time": int(
                        datetime(2024, 1, 5, 23, 59, 0, tzinfo=timezone.utc).timestamp()
                    ),
                },
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
    monkeypatch.setattr(
        "financial_bad_news.pipeline.datetime",
        FixedDatetime,
        raising=False,
    )

    stats = run_pipeline()
    assert stats["inserted"] == 1
    assert stats["processed"] == 1

    with session_scope() as session:
        articles = session.execute(select(NewsArticle)).scalars().all()
        assert len(articles) == 1
        assert articles[0].url == "https://example.com/new"
        assert articles[0].reason and "关键词命中" in articles[0].reason


def test_run_pipeline_deduplicates_by_content(monkeypatch):
    payload_first = {
        "data": {
            "items": [
                {
                    "title": "银行系统漏洞导致信用卡盗刷",
                    "description": "造成用户损失",
                    "url": "https://example.com/a",
                    "time": int(datetime(2024, 1, 5, 8, 0, 0).timestamp()),
                }
            ],
            "totalpage": 1,
        }
    }
    payload_duplicate = {
        "data": {
            "items": [
                {
                    "title": "银行系统漏洞造成信用卡损失",
                    "description": "造成用户资产损失",
                    "url": "https://example.com/copy",
                    "time": int(datetime(2024, 1, 6, 8, 0, 0).timestamp()),
                }
            ],
            "totalpage": 1,
        }
    }

    monkeypatch.setattr(
        "financial_bad_news.pipeline.TophubClient.search",
        lambda self, keyword, page=1, size=50: payload_first,
        raising=False,
    )
    monkeypatch.setattr(
        "financial_bad_news.pipeline.LocalClassifier.classify",
        lambda self, text: (0.2, True),
        raising=False,
    )
    monkeypatch.setattr(
        "financial_bad_news.pipeline.LLMClassifier.classify",
        lambda self, text: ("negative", 0.9),
        raising=False,
    )

    run_pipeline(min_timestamp=datetime(2023, 1, 1))

    monkeypatch.setattr(
        "financial_bad_news.pipeline.TophubClient.search",
        lambda self, keyword, page=1, size=50: payload_duplicate,
        raising=False,
    )

    stats = run_pipeline(min_timestamp=datetime(2023, 1, 1))

    with session_scope() as session:
        articles = session.execute(select(NewsArticle)).scalars().all()
        assert len(articles) == 1
        stored = articles[0]
        assert stored.url == "https://example.com/a"
        assert stored.content_fingerprint is not None
        expected_time = datetime.fromtimestamp(
            payload_duplicate["data"]["items"][0]["time"], tz=timezone.utc
        ).replace(tzinfo=None)
        assert stored.source_timestamp == expected_time

    assert stats["inserted"] == 0
    assert stats["updated"] == 1


def test_run_pipeline_handles_tophub_timeout(monkeypatch):
    def raise_timeout(*_, **__):
        raise requests.exceptions.ReadTimeout("mock timeout")

    monkeypatch.setattr(
        "financial_bad_news.pipeline.TophubClient.search",
        raise_timeout,
        raising=False,
    )

    stats = run_pipeline(min_timestamp=datetime(2023, 1, 1))

    assert stats["inserted"] == 0
    assert stats["processed"] == 0


def test_delete_articles_since_removes_current_day():
    today_start = datetime(2024, 1, 6, 0, 0, 0)
    previous = datetime(2024, 1, 5, 23, 0, 0)

    with session_scope() as session:
        session.add(
            NewsArticle(
                title="今日新闻",
                description="",
                url="https://example.com/today",
                thumbnail=None,
                extra=None,
                source_timestamp=today_start,
                matched_keywords="漏洞",
                local_sentiment_score=0.1,
                local_is_negative=True,
                llm_classification="negative",
                llm_confidence=0.9,
                reason="测试",
                raw_payload={},
            )
        )
        session.add(
            NewsArticle(
                title="昨日新闻",
                description="",
                url="https://example.com/old",
                thumbnail=None,
                extra=None,
                source_timestamp=previous,
                matched_keywords=None,
                local_sentiment_score=None,
                local_is_negative=None,
                llm_classification=None,
                llm_confidence=None,
                reason=None,
                raw_payload={},
            )
        )

    with session_scope() as session:
        removed = delete_articles_since(session, today_start)
        assert removed == 1

    with session_scope() as session:
        remaining_urls = [
            article.url for article in session.execute(select(NewsArticle)).scalars().all()
        ]
        assert remaining_urls == ["https://example.com/old"]
