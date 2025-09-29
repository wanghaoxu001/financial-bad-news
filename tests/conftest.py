"""Pytest fixtures for the financial bad news project."""

from __future__ import annotations

import os
from typing import Iterator

import pytest

from financial_bad_news.config import get_settings
from financial_bad_news.db import init_db, reset_engine


@pytest.fixture(autouse=True)
def configure_environment(tmp_path, monkeypatch) -> Iterator[None]:
    sqlite_path = tmp_path / "test.db"
    env_vars = {
        "LLM_BASE_URL": "https://llm.example.com/v1",
        "LLM_API_KEY": "test-key",
        "LLM_MODEL": "test-model",
        "SQLITE_PATH": str(sqlite_path),
        "FETCH_KEYWORD": "银行",
        "NEGATIVE_KEYWORDS": "盗刷,漏洞",
        "SENTIMENT_NEGATIVE_THRESHOLD": "0.4",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    reset_engine()
    init_db()
    yield
    get_settings.cache_clear()
    reset_engine()
