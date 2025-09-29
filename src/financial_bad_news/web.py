"""Flask UI for debugging the pipeline and viewing articles."""

from __future__ import annotations

from math import ceil

from flask import Flask, Response, jsonify, render_template, request

from .config import Settings, get_settings
from .db import session_scope
from .pipeline import run_pipeline
from .repository import count_articles, list_recent_articles
from .rss import generate_rss
from .scheduler import start_scheduler


def create_app(settings: Settings | None = None, *, enable_scheduler: bool = False) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SETTINGS"] = settings or get_settings()

    if enable_scheduler:
        start_scheduler()

    @app.route("/")
    def dashboard():
        current_settings: Settings = app.config["SETTINGS"]
        page = _parse_positive_int(request.args.get("page"), default=1, minimum=1)
        page_size = _parse_positive_int(
            request.args.get("page_size"), default=20, minimum=5, maximum=200
        )

        with session_scope() as session:
            total_count = count_articles(session)
            total_pages = max(1, ceil(total_count / page_size)) if total_count else 1
            if page > total_pages:
                page = total_pages
            articles = list_recent_articles(session, page=page, page_size=page_size)

        keyword_options = _collect_keywords(articles)
        page_count = len(articles)
        page_size_options = sorted({10, 20, 50, 100, page_size})
        return render_template(
            "dashboard.html",
            settings=current_settings,
            articles=articles,
            keyword_options=keyword_options,
            total_count=total_count,
            total_pages=total_pages,
            page=page,
            page_size=page_size,
            page_count=page_count,
            page_size_options=page_size_options,
        )

    @app.post("/run")
    def run_job():
        data = request.get_json(silent=True) or request.form
        keyword = data.get("keyword")
        negative_keywords = _parse_keywords(data.get("negative_keywords"))
        threshold = _parse_float(data.get("sentiment_threshold"))
        page_size = _parse_int(data.get("page_size"))
        stats = run_pipeline(
            keyword=keyword or None,
            negative_keywords=negative_keywords,
            sentiment_threshold=threshold,
            page_size=page_size,
        )
        return jsonify(stats)

    @app.get("/rss")
    def rss_feed():
        rss_bytes = generate_rss(limit=100)
        return Response(rss_bytes, mimetype="application/rss+xml")

    return app


def _parse_keywords(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    keywords = [segment.strip() for segment in raw.split(",") if segment.strip()]
    return keywords or None


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_positive_int(
    raw: str | None,
    *,
    default: int,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if raw is None or raw == "":
        value = default
    else:
        try:
            value = int(raw)
        except ValueError:
            value = default
    if value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value


def _collect_keywords(articles):
    seen: set[str] = set()
    for article in articles:
        if article.matched_keywords:
            for kw in article.matched_keywords.split(","):
                kw = kw.strip()
                if kw:
                    seen.add(kw)
    return sorted(seen)


__all__ = ["create_app"]
