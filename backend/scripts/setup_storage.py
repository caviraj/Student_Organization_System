"""Create - or verify - the PRIVATE receipts bucket in Supabase Storage.

    python scripts/setup_storage.py

Idempotent, so it is safe to run on every deploy. It exits non-zero if the bucket exists and is
PUBLIC: receipts are a photo of somebody's till slip, and a public bucket is served to anyone with
the URL (DESIGN.md §4 rule 14). The service-role key is read from the environment and never printed.

`STORAGE_PROVIDER=local` has nothing to set up - the dev provider writes into LOCAL_STORAGE_DIR - so
this prints that and succeeds, which is what keeps `seed.py` able to call it unconditionally.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import httpx

from app.core.config import settings
from app.services import storage

TIMEOUT_SECONDS = 10.0


def ensure_bucket() -> int:
    bucket = settings.RECEIPTS_BUCKET
    if settings.STORAGE_PROVIDER != "supabase":
        print(f"  STORAGE_PROVIDER={settings.STORAGE_PROVIDER}: receipts go to {settings.LOCAL_STORAGE_DIR}, nothing to create")
        return 0
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        print("  FAIL: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required when STORAGE_PROVIDER=supabase")
        return 1

    base = settings.SUPABASE_URL.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}", "apikey": settings.SUPABASE_SERVICE_ROLE_KEY}

    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            found = client.get(f"{base}/storage/v1/bucket/{bucket}", headers=headers)
            if found.status_code == 200:
                if found.json().get("public"):
                    print(f"  FAIL: bucket '{bucket}' exists and is PUBLIC - receipts must stay private (DESIGN.md §4 rule 14)")
                    return 1
                print(f"  OK: private bucket '{bucket}' already exists")
                return 0
            if found.status_code != 404:
                print(f"  FAIL: could not read bucket '{bucket}' ({found.status_code})")
                return 1

            created = client.post(
                f"{base}/storage/v1/bucket",
                headers=headers,
                json={
                    "id": bucket,
                    "name": bucket,
                    "public": False,
                    "file_size_limit": storage.MAX_RECEIPT_BYTES,
                    "allowed_mime_types": sorted(storage.EXT_BY_MIME),
                },
            )
            if created.status_code >= 400:
                # The body can echo the request back, so only the status is worth printing.
                print(f"  FAIL: could not create bucket '{bucket}' ({created.status_code})")
                return 1
    except httpx.HTTPError as exc:
        # A DNS failure or a timeout is an ops problem, not a stack trace to hand the operator.
        print(f"  FAIL: could not reach {base} ({type(exc).__name__})")
        return 1

    print(
        f"  OK: created private bucket '{bucket}' "
        f"(max {storage.MAX_RECEIPT_BYTES // (1024 * 1024)} MB, {', '.join(sorted(storage.EXT_BY_MIME))})"
    )
    return 0


def main() -> int:
    print("SSA Hub - receipt storage")
    print("-" * 64)
    print(f"  SUPABASE_URL    {settings.SUPABASE_URL or '(unset)'}")
    print(f"  bucket          {settings.RECEIPTS_BUCKET}")
    code = ensure_bucket()
    print("-" * 64)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
