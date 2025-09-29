"""Background scheduler integration."""

from __future__ import annotations

import atexit
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

from .config import get_settings
from .pipeline import run_pipeline


_scheduler: Optional[BackgroundScheduler] = None


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    settings = get_settings()
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_pipeline,
        "interval",
        minutes=settings.scheduler_interval_minutes,
        id="fetch_financial_news",
        max_instances=1,
        replace_existing=True,
    )
    scheduler.start()

    atexit.register(lambda: scheduler.shutdown(wait=False))
    _scheduler = scheduler
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


__all__ = ["start_scheduler", "stop_scheduler"]

