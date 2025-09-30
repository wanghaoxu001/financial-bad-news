"""Repository utilities for interacting with persisted news articles."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from hashlib import blake2b
from typing import Iterable, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import NewsArticle


SIMHASH_BITS = 64
SIMHASH_FUZZY_LOWER_BITS = 8
SIMHASH_MATCH_THRESHOLD = 24
SIMHASH_CANDIDATE_LIMIT = 500


def _normalize_text(text: str) -> str:
    normalized = " ".join(text.split())
    return normalized.strip()


def _build_simhash_tokens(text: str) -> Counter[str]:
    tokens: Counter[str] = Counter()
    normalized = _normalize_text(text)
    if not normalized:
        return tokens
    for word in normalized.split():
        if word:
            tokens[word] += 1
    condensed = normalized.replace(" ", "")
    if not condensed:
        return tokens
    for char in condensed:
        tokens[char] += 1
    if len(condensed) >= 2:
        for idx in range(len(condensed) - 1):
            tokens[condensed[idx : idx + 2]] += 1
    if len(condensed) <= 3:
        tokens[condensed] += 1
        return tokens
    for idx in range(len(condensed) - 2):
        tokens[condensed[idx : idx + 3]] += 1
    return tokens


def _simhash(tokens: Counter[str]) -> int | None:
    if not tokens:
        return None
    bit_accumulator = [0] * SIMHASH_BITS
    for token, weight in tokens.items():
        digest = blake2b(token.encode("utf-8"), digest_size=SIMHASH_BITS // 8).digest()
        token_hash = int.from_bytes(digest, byteorder="big", signed=False)
        for bit_index in range(SIMHASH_BITS):
            if token_hash & (1 << bit_index):
                bit_accumulator[bit_index] += weight
            else:
                bit_accumulator[bit_index] -= weight
    fingerprint = 0
    for bit_index, value in enumerate(bit_accumulator):
        if value > 0:
            fingerprint |= 1 << bit_index
    if SIMHASH_FUZZY_LOWER_BITS:
        mask = ~((1 << SIMHASH_FUZZY_LOWER_BITS) - 1)
        fingerprint &= mask
    return fingerprint


def _format_simhash(fingerprint: int | None) -> str | None:
    if fingerprint is None:
        return None
    hex_width = SIMHASH_BITS // 4
    return f"{fingerprint:0{hex_width}x}"


def _simhash_distance(hex_a: str, hex_b: str) -> int:
    try:
        value = int(hex_a, 16) ^ int(hex_b, 16)
    except ValueError:
        return SIMHASH_BITS
    return value.bit_count()


def _find_similar_article(session: Session, fingerprint: str) -> NewsArticle | None:
    exact = session.execute(
        select(NewsArticle).where(NewsArticle.content_fingerprint == fingerprint)
    ).scalar_one_or_none()
    if exact is not None:
        return exact
    stmt = (
        select(NewsArticle)
        .where(NewsArticle.content_fingerprint.is_not(None))
        .order_by(NewsArticle.id.desc())
        .limit(SIMHASH_CANDIDATE_LIMIT)
    )
    candidates = session.execute(stmt).scalars()
    closest: NewsArticle | None = None
    best_distance = SIMHASH_BITS + 1
    for candidate in candidates:
        candidate_fp = candidate.content_fingerprint
        if not candidate_fp:
            continue
        distance = _simhash_distance(fingerprint, candidate_fp)
        if distance < best_distance:
            closest = candidate
            best_distance = distance
    if closest is not None and best_distance <= SIMHASH_MATCH_THRESHOLD:
        return closest
    return None


def _compute_content_fingerprint(article: NewsArticle) -> str | None:
    parts: list[str] = []
    if article.title:
        parts.append(article.title.strip())
    if article.description:
        parts.append(article.description.strip())
    if not parts:
        return None
    normalized = " ".join(" ".join(parts).split())
    if not normalized:
        return None
    tokens = _build_simhash_tokens(normalized)
    fingerprint = _simhash(tokens)
    return _format_simhash(fingerprint)


def _ensure_article_fingerprint(article: NewsArticle) -> str | None:
    if article.content_fingerprint:
        return article.content_fingerprint
    fingerprint = _compute_content_fingerprint(article)
    if fingerprint:
        article.content_fingerprint = fingerprint
    return fingerprint


def _locate_existing_article(
    session: Session, article: NewsArticle, fingerprint: str | None
) -> NewsArticle | None:
    if fingerprint:
        existing = _find_similar_article(session, fingerprint)
        if existing is not None:
            return existing
    return session.execute(
        select(NewsArticle).where(NewsArticle.url == article.url)
    ).scalar_one_or_none()


def get_latest_timestamp(session: Session) -> datetime | None:
    stmt = select(NewsArticle.source_timestamp).order_by(NewsArticle.source_timestamp.desc()).limit(1)
    result = session.execute(stmt).scalar_one_or_none()
    return result


def bulk_upsert_articles(session: Session, articles: Iterable[NewsArticle]) -> tuple[int, int]:
    inserted = 0
    updated = 0
    for article in articles:
        fingerprint = _ensure_article_fingerprint(article)
        existing = _locate_existing_article(session, article, fingerprint)
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
            "content_fingerprint",
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
    fingerprint = _ensure_article_fingerprint(article)
    existing = _locate_existing_article(session, article, fingerprint)
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
        "content_fingerprint",
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


def backfill_missing_fingerprints(session: Session) -> int:
    missing_articles = (
        session.execute(
            select(NewsArticle).where(NewsArticle.content_fingerprint.is_(None))
        ).scalars().all()
    )
    updated = 0
    for article in missing_articles:
        fingerprint = _compute_content_fingerprint(article)
        if fingerprint:
            article.content_fingerprint = fingerprint
            updated += 1
    if updated:
        session.flush()
    return updated


__all__ = [
    "get_latest_timestamp",
    "bulk_upsert_articles",
    "list_recent_articles",
    "count_articles",
    "upsert_article",
    "delete_articles_since",
    "backfill_missing_fingerprints",
]
