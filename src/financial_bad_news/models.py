"""ORM models for stored entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (
        UniqueConstraint("url", name="uq_news_url"),
        Index("ix_news_articles_source_timestamp", "source_timestamp"),
        Index("ix_news_articles_content_fingerprint", "content_fingerprint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    thumbnail: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    extra: Mapped[str | None] = mapped_column(String(256), nullable=True)
    content_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=datetime.utcnow, nullable=False
    )

    matched_keywords: Mapped[str | None] = mapped_column(String(512), nullable=True)
    local_sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    local_is_negative: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    llm_classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    llm_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)

    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


__all__ = ["NewsArticle"]
