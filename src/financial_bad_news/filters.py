"""Filtering utilities for news items."""

from __future__ import annotations

from typing import Iterable, List, Mapping


def match_keywords(text: str, keywords: Iterable[str]) -> list[str]:
    lowered = text.lower()
    matched: list[str] = []
    for keyword in keywords:
        normalized = keyword.strip().lower()
        if normalized and normalized in lowered:
            matched.append(keyword.strip())
    return matched


def extract_item_text(item: Mapping[str, str | None]) -> str:
    parts: List[str] = []
    title = item.get("title")
    description = item.get("description")
    if title:
        parts.append(title)
    if description:
        parts.append(description)
    return "。".join(parts)


__all__ = ["match_keywords", "extract_item_text"]

