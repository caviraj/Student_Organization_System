"""Wipe the demo data and rebuild it: the one command that makes a demo reproducible.

    python scripts/reset_demo.py --yes               # the dev database
    python scripts/reset_demo.py --yes --target test # TEST_DATABASE_URL

`seed.py` is idempotent, but idempotent is not the same as *reset*: a demo that went badly (an
order paid twice by hand, a claim reimbursed on stage, a ticket type sold out) is not fixed by
seeding over it, because the seed deliberately leaves existing rows alone. This drops everything
and rebuilds, so the numbers on screen are the numbers in the seed.

**It deletes data.** Three guards, because the cost of being wrong here is somebody's real ledger:

  * `--yes` is required - there is no prompt, so a script that runs in a pipeline cannot hang.
  * `APP_ENV=production` refuses outright, whatever the flags say.
  * A URL equal to `TEST_DATABASE_URL` needs `--target test`: pointing this at the test database
    while meaning the dev one is the exact accident worth blocking.

Everything runs on `DIRECT_URL`, like `seed.py`: TRUNCATE ... CASCADE and the seed's bulk inserts
are one long transaction each, and those do not survive the transaction pooler. `--target test`
switches both URLs to the test database *before* `app.core.db` is imported, so the engine, the
truncate and the seed all land on the same database.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import make_url, text

from app.core.config import settings

SEEDED_PREFIX = "receipts/"
MAX_PREFIX_DEPTH = 4  # receipts/{claimant}/{expense}/{file} - four levels is already generous


def refuse(message: str) -> None:
    print(f"  FAIL: {message}")
    raise SystemExit(1)


def chosen_target(args: list[str]) -> str:
    if "--target" not in args:
        return "dev"
    values = [value for value in args[args.index("--target") + 1 :] if not value.startswith("--")]
    target = values[0] if values else ""
    if target not in ("dev", "test"):
        refuse(f"--target must be dev or test, not '{target}'")
    return target


def resolve_url(target: str) -> str:
    """The database the flags point at, decided before anything is destroyed."""
    if target == "test":
        if not settings.TEST_DATABASE_URL:
            refuse("--target test needs TEST_DATABASE_URL to be set")
        return settings.TEST_DATABASE_URL
    return settings.migration_url


def check_target(target: str, url: str) -> None:
    if settings.is_production:
        refuse("APP_ENV=production - this script truncates every table, whatever the flags say")
    if "pytest" in sys.modules:
        refuse("running inside pytest - this truncates the database it is pointed at")
    if settings.TEST_DATABASE_URL and url == settings.TEST_DATABASE_URL and target != "test":
        refuse("that URL is TEST_DATABASE_URL; pass --target test if the test database is really what you mean")


def truncate_all(engine) -> int:
    """Every table except Alembic's, in one statement, discovered rather than listed: a table added
    in a later phase is cleared without anyone remembering to add it here."""
    with engine.begin() as conn:
        tables = [
            row[0]
            for row in conn.execute(
                text(
                    "select tablename from pg_tables where schemaname = 'public' "
                    "and tablename <> 'alembic_version' order by tablename"
                )
            )
        ]
        if not tables:
            return 0
        conn.execute(text(f"truncate table {', '.join(tables)} restart identity cascade"))
    return len(tables)


def clear_receipts() -> int:
    """The receipt objects the seed wrote. The rows holding their paths are already gone, so
    without this the bucket fills with orphans nobody can reach or account for."""
    from app.services import storage

    if settings.STORAGE_PROVIDER != "supabase":
        root = Path(settings.LOCAL_STORAGE_DIR) / settings.RECEIPTS_BUCKET / "receipts"
        deleted = 0
        for path in sorted(root.rglob("*"), reverse=True) if root.exists() else []:
            if path.is_file():
                path.unlink()
                deleted += 1
            else:
                path.rmdir()
        return deleted

    import httpx

    base = settings.SUPABASE_URL.rstrip("/")
    bucket = settings.RECEIPTS_BUCKET
    headers = {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    }

    # Walk the prefix rather than delete a directory: object storage has no directories, only
    # names that share a prefix, and Supabase's list is one level at a time.
    to_delete: list[str] = []
    queue = [(SEEDED_PREFIX, 0)]
    with httpx.Client(timeout=storage.TIMEOUT_SECONDS) as client:
        while queue:
            prefix, depth = queue.pop()
            response = client.post(
                f"{base}/storage/v1/object/list/{bucket}",
                headers=headers,
                json={"prefix": prefix, "limit": 1000},
            )
            if response.status_code >= 400:
                print(f"  warn: could not list '{prefix}' ({response.status_code}); leaving those objects")
                continue
            for item in response.json():
                name = f"{prefix}{item['name']}"
                if item.get("id") is None and depth < MAX_PREFIX_DEPTH:
                    queue.append((f"{name}/", depth + 1))
                else:
                    to_delete.append(name)

    for name in to_delete:
        client_delete = httpx.request(
            "DELETE", f"{base}/storage/v1/object/{bucket}/{name}", headers=headers, timeout=storage.TIMEOUT_SECONDS
        )
        if client_delete.status_code >= 400:
            print(f"  warn: could not delete '{name}' ({client_delete.status_code})")
    return len(to_delete)


def main() -> int:
    args = sys.argv[1:]
    target = chosen_target(args)
    url = resolve_url(target)
    parsed = make_url(url)

    print("SSA Hub - reset demo data")
    print("-" * 64)
    print(f"  target          {target}")
    print(f"  database        {parsed.host}:{parsed.port}/{parsed.database} (via DIRECT_URL)")
    print(f"  APP_ENV         {settings.APP_ENV}")
    print(f"  storage         {settings.STORAGE_PROVIDER}")

    check_target(target, url)
    if "--yes" not in args:
        print("-" * 64)
        print("  FAIL: this DELETES every row in that database and reseeds it.")
        print("  Re-run with --yes once you are sure that is the database you meant.")
        return 1

    if target == "test":
        # Both URLs point at the test database from here on, so `app.core.db` - imported below,
        # after this point - builds its engines against it and the seed follows.
        settings.DATABASE_URL = url
        settings.DIRECT_URL = url

    from app.core.db import MigrationSessionLocal, migration_engine
    from app.services import storage

    print("-" * 64)
    print(f"  truncated       {truncate_all(migration_engine)} tables (restart identity, cascade)")
    print(f"  receipts        {clear_receipts()} object(s) deleted from the '{settings.RECEIPTS_BUCKET}' bucket")
    storage.reset_provider()
    MigrationSessionLocal.remove() if hasattr(MigrationSessionLocal, "remove") else None

    print("-" * 64)
    print("  reseeding...")
    print()
    from scripts.seed import main as seed_main

    seed_main()
    print()
    print("-" * 64)
    print("  OK: the demo database is back to a freshly seeded state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
