"""Repository utilities for interacting with persisted news articles."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import NewsArticle


def get_latest_timestamp(session: Session) -> datetime | None:
    stmt = select(NewsArticle.source_timestamp).order_by(NewsArticle.source_timestamp.desc()).limit(1)
    result = session.execute(stmt).scalar_one_or_none()
    return result


def bulk_upsert_articles(session: Session, articles: Iterable[NewsArticle]) -> tuple[int, int]:
    inserted = 0
    updated = 0
    for article in articles:
        existing = session.execute(
            select(NewsArticle).where(NewsArticle.url == article.url)
        ).scalar_one_or_none()
        if existing is None:
            session.add(article)
            inserted += 1
            continue
        updated_fields = {}
        for field in (
            "title",
            "description",
            "thumbnail",
            "extra",
            "source_timestamp",
            "matched_keywords",
            "local_sentiment_score",
            "local_is_negative",
            "llm_classification",
            "llm_confidence",
            "reason",
            "raw_payload",
        ):
            new_value = getattr(article, field)
            if new_value != getattr(existing, field):
                setattr(existing, field, new_value)
                updated_fields[field] = new_value
        if updated_fields:
            updated += 1
    try:
        session.flush()
    except IntegrityError as exc:  # pragma: no cover - indicates schema issue
        session.rollback()
        raise ValueError("Failed to upsert articles") from exc
    return inserted, updated


def list_recent_articles(
    session: Session,
    *,
    page: int,
    page_size: int,
) -> Sequence[NewsArticle]:
    stmt = (
        select(NewsArticle)
        .order_by(NewsArticle.source_timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(session.execute(stmt).scalars())


def upsert_article(session: Session, article: NewsArticle) -> tuple[bool, bool]:
    existing = session.execute(
        select(NewsArticle).where(NewsArticle.url == article.url)
    ).scalar_one_or_none()
    if existing is None:
        session.add(article)
        session.flush()
        return True, False

    updated = False
    for field in (
        "title",
        "description",
        "thumbnail",
        "extra",
        "source_timestamp",
        "matched_keywords",
        "local_sentiment_score",
        "local_is_negative",
        "llm_classification",
        "llm_confidence",
        "reason",
        "raw_payload",
    ):
        new_value = getattr(article, field)
        if new_value != getattr(existing, field):
            setattr(existing, field, new_value)
            updated = True
    if updated:
        session.flush()
    return False, updated


def delete_articles_since(session: Session, since: datetime) -> int:
    stmt = delete(NewsArticle).where(NewsArticle.source_timestamp >= since)
    result = session.execute(stmt)
    session.flush()
    return result.rowcount or 0


def count_articles(session: Session) -> int:
    return session.execute(select(func.count(NewsArticle.id))).scalar_one()


__all__ = [
    "get_latest_timestamp",
    "bulk_upsert_articles",
    "list_recent_articles",
    "count_articles",
    "upsert_article",
    "delete_articles_since",
]
