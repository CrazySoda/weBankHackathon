"""Create the schema and apply row-level security + the append-only audit grants.

The ORM creates the tables; ``init/002_rls.sql`` then secures them. Both steps
are idempotent, so this is safe to run on every start.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event

from app.db.models import Base

RLS_SQL = Path(__file__).parent / "init" / "002_rls.sql"


def apply_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    # Raw cursor with no parameters: the script is sent as-is (one multi-statement
    # simple query), so the ``%I`` in its format() calls are not read as placeholders.
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        try:
            cur.execute(RLS_SQL.read_text(encoding="utf-8"))
        finally:
            cur.close()
        raw.commit()
    finally:
        raw.close()


def app_role_engine(url: str) -> Engine:
    """Engine that runs as the unprivileged ``cleartrade_app`` role, so row-level
    security and the audit REVOKEs actually bind. The owner/superuser the URL logs in
    as bypasses both, so the application must never query as that role directly."""
    engine = create_engine(url, pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _assume_app_role(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("SET ROLE cleartrade_app")
        cur.close()
        dbapi_conn.commit()

    return engine
