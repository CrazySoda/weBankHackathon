"""Create the schema and apply row-level security + the append-only audit grants.

The ORM creates the tables; ``init/002_rls.sql`` then secures them. Both steps
are idempotent, so this is safe to run on every start.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine

from app.db.models import Base

RLS_SQL = Path(__file__).parent / "init" / "002_rls.sql"


def apply_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    # Raw cursor with no parameters: the script is sent as-is (one multi-statement
    # simple query), so the ``%I`` in its format() calls are not read as placeholders.
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(RLS_SQL.read_text(encoding="utf-8"))
        raw.commit()
    finally:
        raw.close()
