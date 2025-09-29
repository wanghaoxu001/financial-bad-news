"""Database setup for persisting news articles."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _build_sqlite_url(path: str) -> str:
    db_path = Path(path)
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    resolved = db_path.resolve()
    return f"sqlite+pysqlite:///{resolved}"  # pragma: no cover - deterministic path


def _create_engine() -> Engine:
    settings = get_settings()
    url = _build_sqlite_url(settings.sqlite_path)
    return create_engine(url, echo=False, future=True)


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _create_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), class_=Session, autoflush=False, expire_on_commit=False
        )
    return _session_factory


def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    from . import models  # noqa: F401 - ensure models are imported

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_reason_column(engine)


def _ensure_reason_column(engine: Engine) -> None:
    inspector = inspect(engine)
    try:
        columns = {column["name"] for column in inspector.get_columns("news_articles")}
    except Exception:  # pragma: no cover - unexpected inspector failure
        return
    if "reason" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE news_articles ADD COLUMN reason TEXT"))


__all__ = [
    "Base",
    "get_engine",
    "get_session_factory",
    "reset_engine",
    "session_scope",
    "init_db",
]
