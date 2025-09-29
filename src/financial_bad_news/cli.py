"""Command line interface for the financial bad news project."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .db import session_scope
from .pipeline import run_pipeline
from .repository import delete_articles_since
from .rss import generate_rss
from .scheduler import start_scheduler, stop_scheduler


def _parse_keywords(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _configure_logging(level: str | None) -> None:
    if level is None:
        return
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"未知日志级别: {level}")
    logging.basicConfig(level=numeric_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError as exc:  # pragma: no cover - user input error
        raise SystemExit(f"无法解析 min-timestamp: {value}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Financial bad news utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Run one fetch-classify cycle")
    fetch_parser.add_argument("--keyword", help="Override the search keyword", default=None)
    fetch_parser.add_argument(
        "--keywords", help="Override negative keywords (comma separated)", default=None
    )
    fetch_parser.add_argument(
        "--threshold", type=float, help="Override negative sentiment threshold", default=None
    )
    fetch_parser.add_argument(
        "--page-size", type=int, help="Override page size for the search", default=None
    )
    fetch_parser.add_argument(
        "--log-level",
        default="INFO",
        help="日志级别，例如 INFO、DEBUG",
    )
    fetch_parser.add_argument(
        "--min-timestamp",
        help="自定义最早新闻时间 (ISO 格式, 例如 2024-01-01T00:00:00)",
        default=None,
    )

    rss_parser = subparsers.add_parser("rss", help="Generate RSS feed")
    rss_parser.add_argument("--limit", type=int, default=50, help="Number of articles to include")
    rss_parser.add_argument("--output", help="Output file path; prints to stdout if omitted")

    scheduler_parser = subparsers.add_parser("scheduler", help="Start the recurring scheduler")
    scheduler_parser.add_argument(
        "--log-level",
        default="INFO",
        help="日志级别，例如 INFO、DEBUG",
    )

    clear_parser = subparsers.add_parser("clear-today", help="Remove news stored for today")
    clear_parser.add_argument(
        "--log-level",
        default="INFO",
        help="日志级别，例如 INFO、DEBUG",
    )

    serve_parser = subparsers.add_parser("serve", help="Run Flask UI with scheduler")
    serve_parser.add_argument(
        "--host", default="127.0.0.1", help="Host for the development server"
    )
    serve_parser.add_argument("--port", type=int, default=5000, help="Port for the server")

    args = parser.parse_args(argv)

    if args.command == "fetch":
        _configure_logging(args.log_level)
        stats = run_pipeline(
            keyword=args.keyword,
            negative_keywords=_parse_keywords(args.keywords),
            sentiment_threshold=args.threshold,
            page_size=args.page_size,
            min_timestamp=_parse_datetime(args.min_timestamp),
        )
        print(
            "Inserted: {inserted}, Updated: {updated}, Fetched: {fetched}, Processed: {processed}".format(
                **stats
            )
        )
        return 0

    if args.command == "rss":
        rss_data = generate_rss(limit=args.limit)
        if args.output:
            path = Path(args.output)
            path.write_bytes(rss_data)
            print(f"RSS feed written to {path}")
        else:
            sys.stdout.buffer.write(rss_data)
        return 0

    if args.command == "scheduler":
        _configure_logging(args.log_level)
        scheduler = start_scheduler()
        print("Scheduler started. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("Stopping scheduler...")
            stop_scheduler()
        return 0

    if args.command == "clear-today":
        _configure_logging(args.log_level)
        start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        with session_scope() as session:
            removed = delete_articles_since(session, start)
        print(f"已删除 {removed} 条 {start.date()} 起的新闻")
        return 0

    if args.command == "serve":
        from .web import create_app

        app = create_app(enable_scheduler=True)
        app.run(host=args.host, port=args.port, debug=True)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
