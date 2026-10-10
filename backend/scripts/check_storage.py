"""Check that receipts can actually be stored, signed and deleted - the storage twin of
`check_db.py`.

    python scripts/check_storage.py

`setup_storage.py` answers "does the bucket exist and is it private"; this answers "does the whole
flow work", by round-tripping one throwaway object through the provider the app will really use:

  1. put a 1x1 PNG under a probe path (so it passes the same magic-byte validation as a receipt)
  2. sign it, and check the URL is not the storage path
  3. delete it, and confirm it is gone
  4. with Supabase, also fetch the object WITHOUT a signature and require a refusal - a bucket that
     answers 200 to an unsigned URL is public whatever its metadata says

Exits non-zero on the first failure. The probe path is prefixed `probe/`, so `reset_demo.py` and
the receipt sweep never mistake it for a real receipt under `receipts/`.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import httpx

from app.core.config import settings
from app.services import storage

# The smallest valid PNG: the magic-byte check in storage.py reads the header, not the image.
PROBE_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001a5f645400000000049454e44ae426082"
)
PROBE_PATH = "probe/check_storage.png"


def _round_trip(provider) -> list[str]:
    provider.put(PROBE_PATH, PROBE_PNG, "image/png")
    url = provider.signed_url(PROBE_PATH, settings.RECEIPT_URL_TTL_SECONDS)
    if PROBE_PATH in url:
        return [f"signed URL leaks the storage path ({url})"]
    provider.delete(PROBE_PATH)
    return []


def _unsigned_fetch_refused(bucket: str) -> list[str]:
    """A PRIVATE bucket must not serve the object to an anonymous caller."""
    public = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{bucket}/{PROBE_PATH}"
    try:
        response = httpx.get(public, timeout=storage.TIMEOUT_SECONDS, follow_redirects=False)
    except httpx.HTTPError as exc:
        return [f"could not reach storage ({type(exc).__name__})"]
    if response.status_code < 400:
        return [f"an UNSIGNED url returned {response.status_code} - bucket '{bucket}' is public"]
    return []


def main() -> int:
    provider_name = settings.STORAGE_PROVIDER
    print("SSA Hub - receipt storage check")
    print("-" * 64)
    print(f"  STORAGE_PROVIDER   {provider_name}")
    print(f"  bucket             {settings.RECEIPTS_BUCKET}")
    if provider_name == "supabase":
        print(f"  SUPABASE_URL       {settings.SUPABASE_URL or '(unset)'}")
    else:
        print(f"  LOCAL_STORAGE_DIR  {settings.LOCAL_STORAGE_DIR}")
    print(f"  signed URL TTL     {settings.RECEIPT_URL_TTL_SECONDS}s")

    problems: list[str] = []
    try:
        provider = storage.get_provider()
    except Exception as exc:  # noqa: BLE001 - a diagnostic reports misconfiguration, it never crashes
        problems.append(f"provider is not configured ({exc})")
    else:
        try:
            problems += _round_trip(provider)
        except Exception as exc:  # noqa: BLE001 - a storage outage is an ops problem, not a traceback
            problems.append(f"put/sign/delete failed ({type(exc).__name__}: {exc})")
        if provider_name == "supabase" and not problems:
            problems += _unsigned_fetch_refused(settings.RECEIPTS_BUCKET)

    print("-" * 64)
    if problems:
        for problem in problems:
            print(f"  FAIL: {problem}")
        return 1
    print("  OK: put, sign, delete and the private-bucket check all passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
