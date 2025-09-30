from __future__ import annotations

import httpx

from financial_bad_news.classification import LLMClassifier


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_llm_classifier_retries_and_succeeds(monkeypatch):
    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ReadTimeout("timeout")
        return _DummyResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"label": "negative", "confidence": 0.8}'
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("financial_bad_news.classification.httpx.post", fake_post)
    monkeypatch.setattr("financial_bad_news.classification.time.sleep", lambda _: None)

    classifier = LLMClassifier(
        base_url="https://api.example.com",
        api_key="token",
        model="model",
        timeout=1.0,
        max_retries=2,
        retry_delay=0.0,
    )

    label, confidence = classifier.classify("测试文本")

    assert calls["count"] == 2
    assert label == "negative"
    assert confidence == 0.8


def test_llm_classifier_returns_error_after_retries(monkeypatch):
    def raise_error(*args, **kwargs):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr("financial_bad_news.classification.httpx.post", raise_error)
    monkeypatch.setattr("financial_bad_news.classification.time.sleep", lambda _: None)

    classifier = LLMClassifier(
        base_url="https://api.example.com",
        api_key="token",
        model="model",
        timeout=1.0,
        max_retries=1,
        retry_delay=0.0,
    )

    label, confidence = classifier.classify("测试文本")

    assert label == "error"
    assert confidence == 0.0
