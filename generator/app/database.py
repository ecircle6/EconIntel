"""SQLite 连接管理（WAL 模式；写入集中在主线程，避免锁竞争）。"""
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

_engine = None
_session_factory = None


def get_engine(db_path: Path):
    global _engine, _session_factory
    if _engine is None:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_path.as_posix()}",
            connect_args={"check_same_thread": False},
            future=True,
        )

        @event.listens_for(_engine, "connect")
        def _set_pragma(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        _session_factory = sessionmaker(bind=_engine, future=True, expire_on_commit=False)
    return _engine


def init_db(db_path: Path) -> None:
    from . import models  # noqa: F401  确保模型注册

    get_engine(db_path)
    Base.metadata.create_all(_engine)


def get_session():
    if _session_factory is None:
        raise RuntimeError("请先调用 init_db(db_path)")
    return _session_factory()
