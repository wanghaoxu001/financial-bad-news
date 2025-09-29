"""RSS feed generation utilities."""

from __future__ import annotations

from datetime import timezone
from html import escape

from feedgen.feed import FeedGenerator

from .config import get_settings
from .repository import list_recent_articles
from .db import session_scope


def generate_rss(limit: int = 50) -> bytes:
    settings = get_settings()

    with session_scope() as session:
        articles = list_recent_articles(session, page=1, page_size=limit)

    fg = FeedGenerator()
    fg.id("financial-bad-news")
    fg.title("金融负面新闻监控")
    fg.author({"name": "Financial Bad News"})
    fg.link(href="http://localhost/rss", rel="self")
    fg.language("zh")
    fg.description("银行及金融业负面新闻聚合RSS")

    for article in articles:
        entry = fg.add_entry()
        entry.id(article.url)
        entry.title(article.title)
        entry.link(href=article.url)
        entry.summary(_build_summary(article), type="html")
        published = article.source_timestamp.replace(tzinfo=timezone.utc)
        entry.published(published)
        if article.matched_keywords:
            entry.category(term=article.matched_keywords)

    return fg.rss_str(pretty=True)


def _build_summary(article) -> str:
    parts = ["<div style='font-family: sans-serif;'>"]
    if article.description:
        parts.append(f"<p>{escape(article.description)}</p>")
    if article.matched_keywords:
        parts.append(
            "<p><strong>匹配关键词：</strong>" + escape(article.matched_keywords) + "</p>"
        )
    if article.local_sentiment_score is not None:
        sentiment_label = "负面" if article.local_is_negative else "非负面"
        parts.append(
            "<p><strong>本地情感：</strong>"
            + f"{article.local_sentiment_score:.2f} ({sentiment_label})"
            + "</p>"
        )
    if article.llm_classification:
        label_map = {"negative": "负面", "neutral": "中性", "positive": "正面"}
        label = label_map.get((article.llm_classification or "").lower(), article.llm_classification)
        confidence = article.llm_confidence or 0.0
        parts.append(
            "<p><strong>LLM 判定：</strong>"
            + escape(label)
            + f"，置信度 {confidence:.2f}"
            + "</p>"
        )
    if article.reason:
        parts.append("<p><strong>过滤理由：</strong>" + escape(article.reason) + "</p>")
    parts.append("</div>")
    return "".join(parts)


__all__ = ["generate_rss"]
