"""Database preflight: is the app pointed at the right place, and is the data locked down?

    python scripts/check_db.py

Prints the connection the app will actually use (server version, database, and whether traffic
goes through the transaction pooler), then every table in the public schema with its Row Level
Security state. Exits non-zero if any table has RLS disabled.

RLS matters here because Supabase publishes the public schema over its own REST API. Our FastAPI
backend connects as the table owner and is unaffected, but without RLS any anonymous visitor could
read every member, order and payment through that API. No policies + RLS on = nobody but the owner.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import make_url, text

from app.core.config import settings
from app.core.db import engine

POOLER_PORTS = {6543: "transaction pooler", 5432: "session pooler / direct"}


def main() -> int:
    url = make_url(settings.DATABASE_URL)
    print("SSA Hub - database check")
    print("-" * 64)
    print(f"  DATABASE_URL    {url.host}:{url.port}/{url.database}")
    print(f"  DIRECT_URL      {make_url(settings.migration_url).host or '(same as DATABASE_URL)'}")
    print(f"  mode            {POOLER_PORTS.get(url.port, 'direct')}")
    if "pooler.supabase.com" not in (url.host or ""):
        print("  note            host is not a Supabase pooler - local dev? prepared statements stay off anyway")

    with engine.connect() as conn:
        version = conn.execute(text("select version()")).scalar()
        database = conn.execute(text("select current_database()")).scalar()
        user = conn.execute(text("select current_user")).scalar()
        print(f"  server          {version.split(',')[0]}")
        print(f"  connected as    {user} @ {database}")
        if url.port == 6543:
            backend_port = conn.execute(text("select inet_server_port()")).scalar()
            print(f"  backend session real port {backend_port} (pooled) - no session state, no advisory locks")

        rows = conn.execute(
            text(
                # alembic_version is exempt: it holds one revision id and is Alembic's own table
                # (AGENTS.md, Backend rules).
                "select tablename, rowsecurity from pg_tables "
                "where schemaname = 'public' and tablename <> 'alembic_version' order by tablename"
            )
        ).all()

    if not rows:
        print("\n  no tables in the public schema - run `python -m alembic upgrade head` first")
        return 1

    unprotected = [name for name, rls in rows if not rls]
    print(f"\n  {'table':<32} rls")
    print(f"  {'-' * 32} -----")
    for name, rls in rows:
        print(f"  {name:<32} {'on' if rls else 'OFF  <-- exposed!'}")

    print("-" * 64)
    if unprotected:
        print(f"  FAIL: {len(unprotected)} table(s) without RLS: {', '.join(unprotected)}")
        print("  Supabase publishes the public schema over REST; enable RLS (AGENTS.md, Backend rules).")
        return 1
    print(f"  OK: RLS enabled on all {len(rows)} public tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
