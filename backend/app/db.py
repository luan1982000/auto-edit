from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def init_db(db_path: Path) -> None:
    """Create the engine and tables. Safe to call repeatedly (e.g. in tests)."""
    global _engine, _session_factory
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    _session_factory = sessionmaker(bind=_engine, class_=Session, expire_on_commit=False)
    SQLModel.metadata.create_all(_engine)
    _migrate_settings(_engine)


def _migrate_settings(engine: Engine) -> None:
    """Add columns introduced after the first local release.

    `create_all` never alters an existing table, so old `data/app.db` files
    need an explicit, idempotent ALTER.
    """
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(settings)").fetchall()
        columns = {row[1] for row in rows}
        if columns and "render_preset" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE settings ADD COLUMN render_preset "
                "VARCHAR NOT NULL DEFAULT 'full'"
            )


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _session_factory


def get_session() -> Iterator[Session]:
    with get_session_factory()() as session:
        yield session
