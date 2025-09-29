"""News classification helpers."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Tuple

import httpx
from snownlp import SnowNLP


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LocalClassifier:
    negative_threshold: float = 0.45

    def classify(self, text: str) -> tuple[float, bool]:
        try:
            sentiment = SnowNLP(text).sentiments
        except Exception:  # pragma: no cover - underlying NLP failure
            sentiment = 0.5
        is_negative = sentiment < self.negative_threshold
        return sentiment, is_negative


class LLMClassifier:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 15.0) -> None:
        self.endpoint = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def classify(self, text: str) -> tuple[str, float]:
        if not self.api_key:
            return "not_configured", 0.0
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": 0.0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一个金融新闻分类助手。请判断用户提供的新闻是否描述了"
                        "与银行或金融机构相关的负面事件。只返回JSON，格式为"
                        " {\"label\": \"negative|neutral|positive\", \"confidence\": 0.0-1.0}."
                    ),
                },
                {"role": "user", "content": text},
            ],
        }
        try:
            response = httpx.post(self.endpoint, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            content = self._extract_content(data)
            parsed = self._parse_json_content(content)
            label = str(parsed.get("label", "unknown")).lower()
            confidence_raw = parsed.get("confidence", 0.0)
            try:
                confidence = float(confidence_raw)
            except (TypeError, ValueError):
                confidence = 0.0
            return label, confidence
        except Exception as exc:  # pragma: no cover - network or parsing failure
            logger.warning("LLM 分类失败: %s", exc, exc_info=True)
            return "error", 0.0

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
        raise ValueError("Unexpected response payload from LLM")

    @staticmethod
    def _parse_json_content(content: str) -> dict[str, Any]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if "{" not in cleaned:
                raise ValueError("No JSON found in fenced content")
            cleaned = cleaned[cleaned.find("{") : cleaned.rfind("}") + 1]
        else:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(0)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:  # pragma: no cover - log unexpected format
            logger.error("LLM 返回内容无法解析为 JSON: %s", cleaned)
            raise


__all__ = ["LocalClassifier", "LLMClassifier"]
