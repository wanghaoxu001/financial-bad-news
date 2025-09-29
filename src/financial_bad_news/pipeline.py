"""Core pipeline to fetch, filter, classify, and persist news articles."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from itertools import count
from typing import Iterable, Mapping, MutableMapping

from .classification import LLMClassifier, LocalClassifier
from .config import get_settings
from .db import init_db, session_scope
from .filters import extract_item_text, match_keywords
from .models import NewsArticle
from .repository import get_latest_timestamp, upsert_article
from .tophub_client import TophubClient


logger = logging.getLogger(__name__)

_LLM_LABEL_MAP = {"negative": "负面", "neutral": "中性", "positive": "正面"}


class PipelineStats(dict):
    inserted: int
    updated: int
    fetched: int
    processed: int


def run_pipeline(
    *,
    keyword: str | None = None,
    negative_keywords: list[str] | None = None,
    sentiment_threshold: float | None = None,
    page_size: int | None = None,
    min_timestamp: datetime | None = None,
    ) -> PipelineStats:
    settings = get_settings()
    init_db()
    client = TophubClient(
        api_key=settings.tophub_api_key,
        base_url=str(settings.tophub_base_url),
    )
    local_classifier = LocalClassifier(
        negative_threshold=(
            sentiment_threshold
            if sentiment_threshold is not None
            else settings.sentiment_negative_threshold
        )
    )
    llm_classifier = LLMClassifier(
        base_url=str(settings.llm_base_url),
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )

    keywords = negative_keywords if negative_keywords is not None else settings.keywords_list()
    fetched_items = 0
    processed_items = 0
    inserted_count = 0
    updated_count = 0

    with session_scope() as session:
        last_timestamp = get_latest_timestamp(session)
        effective_min_timestamp = min_timestamp
        if effective_min_timestamp is None and last_timestamp is None:
            now = datetime.utcnow()
            effective_min_timestamp = now.replace(hour=0, minute=0, second=0, microsecond=0)

        logger.info(
            "启动拉取：keyword=%s page_size=%s min_timestamp=%s last_timestamp=%s",
            keyword or settings.fetch_keyword,
            page_size or settings.page_size,
            effective_min_timestamp,
            last_timestamp,
        )
        for page in count(1):
            logger.info("请求 TopHub 第 %s 页", page)
            payload = client.search(
                keyword or settings.fetch_keyword,
                page=page,
                size=page_size or settings.page_size,
            )
            items = _extract_items(payload)
            if not items:
                logger.info("第 %s 页无数据，停止拉取", page)
                break
            stop_paging = False
            logger.info("第 %s 页返回 %s 条", page, len(items))
            for item in items:
                fetched_items += 1
                article_time = _parse_timestamp(item.get("time"))
                if article_time is None:
                    logger.debug("跳过缺少时间戳的新闻：%s", item.get("title"))
                    continue
                if last_timestamp and article_time <= last_timestamp:
                    logger.info(
                        "遇到已存在的新闻时间戳 %s (<= %s)，准备停止翻页",
                        article_time,
                        last_timestamp,
                    )
                    stop_paging = True
                    continue
                if effective_min_timestamp and article_time < effective_min_timestamp:
                    logger.info(
                        "新闻时间戳 %s 早于最小时间 %s，准备停止翻页",
                        article_time,
                        effective_min_timestamp,
                    )
                    stop_paging = True
                    continue

                text = extract_item_text(item)
                matched = match_keywords(text, keywords)
                if not matched:
                    logger.debug("未命中关键词，跳过：%s", item.get("title"))
                    continue

                local_score, local_negative = local_classifier.classify(text)
                llm_label, llm_confidence = llm_classifier.classify(text)

                url = item.get("url")
                if not url:
                    logger.debug("缺少 URL，跳过：%s", item.get("title"))
                    continue

                reason = _build_reason(matched, local_score, local_negative, llm_label, llm_confidence)

                article = NewsArticle(
                    title=item.get("title") or "",
                    description=item.get("description") or "",
                    url=str(url),
                    thumbnail=item.get("thumbnail"),
                    extra=item.get("extra"),
                    source_timestamp=article_time,
                    matched_keywords=",".join(matched) if matched else None,
                    local_sentiment_score=local_score,
                    local_is_negative=local_negative,
                    llm_classification=llm_label,
                    llm_confidence=llm_confidence,
                    reason=reason,
                    raw_payload=dict(item),
                )
                processed_items += 1
                inserted, updated = upsert_article(session, article)
                if inserted:
                    inserted_count += 1
                if updated:
                    updated_count += 1
                if inserted or updated:
                    session.commit()
                logger.info(
                    "命中新闻：%s | 关键词=%s | 本地情感=%.2f | LLM=%s | 理由=%s | 动作=%s",
                    article.title,
                    ",".join(matched),
                    local_score,
                    llm_label,
                    reason,
                    "插入" if inserted else "更新" if updated else "无变化",
                )
            if stop_paging:
                logger.info("满足停止条件，结束翻页")
                break
            total_pages = _extract_total_pages(payload)
            if total_pages is not None and page >= total_pages:
                logger.info("到达最后一页 %s，结束翻页", total_pages)
                break

    stats: PipelineStats = {
        "inserted": inserted_count,
        "updated": updated_count,
        "fetched": fetched_items,
        "processed": processed_items,
    }
    logger.info(
        "拉取完成：inserted=%s updated=%s fetched=%s processed=%s",
        inserted_count,
        updated_count,
        fetched_items,
        processed_items,
    )
    return stats


def _extract_items(payload: MutableMapping[str, object]) -> Iterable[Mapping[str, object]]:
    data = payload.get("data")
    if isinstance(data, Mapping):
        items = data.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, Mapping)]
    return []


def _extract_total_pages(payload: MutableMapping[str, object]) -> int | None:
    data = payload.get("data")
    if isinstance(data, Mapping):
        total_page = data.get("totalpage")
        if isinstance(total_page, int):
            return total_page
    return None


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
    if isinstance(value, str) and value.isdigit():
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
    return None


def _build_reason(
    matched_keywords: list[str],
    local_score: float,
    local_negative: bool,
    llm_label: str,
    llm_confidence: float,
) -> str:
    parts: list[str] = []
    if matched_keywords:
        parts.append(f"关键词命中：{','.join(matched_keywords)}")
    parts.append(
        f"本地情感：{local_score:.2f} ({'负面' if local_negative else '非负面'})"
    )
    if llm_label:
        label_text = _LLM_LABEL_MAP.get(llm_label.lower(), llm_label)
        parts.append(f"LLM 判定：{label_text} (置信度 {llm_confidence:.2f})")
    return "；".join(parts)


__all__ = ["run_pipeline"]
