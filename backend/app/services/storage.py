"""Receipt storage — a PRIVATE bucket, reached only by this backend (DESIGN.md §4 rule 14).

Receipts are the most sensitive thing the club holds: a photo of somebody's till slip. So:

* the bucket is private, and the **service-role key never leaves the server** — it is never logged,
  never returned, and never put in a URL we hand out;
* the API never returns `receipt_path`. It returns a **signed URL** that expires in ten minutes
  (`GET /expenses/{id}/receipt`), minted fresh per request;
* the path is built by us from the claimant and expense ids plus a fresh uuid — the client's
  filename is never used, so `../../etc/passwd` and friends cannot reach the bucket;
* the bytes are checked against their declared type by magic number, because a
  `Content-Type: image/png` header is a claim, not a fact.

Blocking HTTP: `httpx` calls are synchronous, so every caller must already be off the event loop
(the receipt endpoints run their service call in a threadpool). One retry on 5xx, 10s timeout —
Supabase Storage is a second service and a transient 502 should not lose a volunteer's receipt.
"""

from pathlib import PurePosixPath
from uuid import UUID, uuid4

import httpx
from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import AppError

MAX_RECEIPT_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 10.0

EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}

# The shortest prefix that identifies each format unambiguously. webp is RIFF-based, so its
# signature is split: "RIFF" at 0 and "WEBP" at 8.
_MAGIC = {
    "image/jpeg": ((0, b"\xff\xd8\xff"),),
    "image/png": ((0, b"\x89PNG\r\n\x1a\n"),),
    "image/webp": ((0, b"RIFF"), (8, b"WEBP")),
    "application/pdf": ((0, b"%PDF-"),),
}


def validate_receipt(data: bytes, declared_mime: str) -> str:
    """Checks the declared type, the size, and the bytes themselves. Returns the file extension.

    The magic-number check is the point: a `.pdf` full of HTML is rejected here rather than stored
    and later handed to a browser as a document.
    """
    declared_mime = (declared_mime or "").split(";")[0].strip().lower()
    if declared_mime not in EXT_BY_MIME:
        raise AppError(
            422,
            "INVALID_FILE_TYPE",
            "A receipt must be a JPEG, PNG, WebP or PDF",
            {"declared_mime": declared_mime, "allowed": sorted(EXT_BY_MIME)},
        )
    if len(data) > MAX_RECEIPT_BYTES:
        raise AppError(
            413,
            "FILE_TOO_LARGE",
            f"A receipt may be at most {MAX_RECEIPT_BYTES // (1024 * 1024)} MB",
            {"size": len(data), "max_bytes": MAX_RECEIPT_BYTES},
        )
    if not data:
        raise AppError(422, "INVALID_FILE_TYPE", "The uploaded file is empty", {})
    for offset, signature in _MAGIC[declared_mime]:
        if data[offset : offset + len(signature)] != signature:
            raise AppError(
                422,
                "INVALID_FILE_TYPE",
                "The file's contents do not match its declared type",
                {"declared_mime": declared_mime},
            )
    return EXT_BY_MIME[declared_mime]


async def read_upload(upload: UploadFile) -> bytes:
    """Reads at most MAX+1 bytes: one byte past the limit is all it takes to know it is over."""
    data = await upload.read(MAX_RECEIPT_BYTES + 1)
    if len(data) > MAX_RECEIPT_BYTES:
        raise AppError(
            413,
            "FILE_TOO_LARGE",
            f"A receipt may be at most {MAX_RECEIPT_BYTES // (1024 * 1024)} MB",
            {"max_bytes": MAX_RECEIPT_BYTES},
        )
    return data


def receipt_path(claimant_id: UUID, expense_id: UUID, mime: str) -> str:
    """`receipts/{claimant}/{expense}/{uuid}.{ext}` — never the client's filename."""
    return f"receipts/{claimant_id}/{expense_id}/{uuid4()}.{EXT_BY_MIME[mime]}"


# --- providers --------------------------------------------------------------------------------


class StorageProvider:
    """The three things the app needs from a blob store. Nothing here returns a public URL."""

    def put(self, path: str, data: bytes, mime: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def signed_url(self, path: str, expires_in: int) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def delete(self, path: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class LocalStorageProvider(StorageProvider):
    """Filesystem-backed, for `STORAGE_PROVIDER=local` and the test suite.

    `signed_url` deliberately does NOT hand back the storage path: the API's contract is "a signed
    URL, never the path", and a dev provider that leaked the path would make the tests that prove
    it pass for the wrong reason.

    shortcut: the token is not verified by anything, because nothing serves these files; use
    STORAGE_PROVIDER=supabase to actually download a receipt.
    """

    def __init__(self, root: str, bucket: str):
        self.root = PurePosixPath(root)
        self.bucket = bucket

    def _full(self, path: str):
        from pathlib import Path

        return Path(str(self.root)) / self.bucket / path

    def put(self, path: str, data: bytes, mime: str) -> None:
        target = self._full(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def signed_url(self, path: str, expires_in: int) -> str:
        token = uuid4().hex
        return f"http://local-storage.invalid/signed/{token}?expires_in={expires_in}"

    def delete(self, path: str) -> None:
        self._full(path).unlink(missing_ok=True)


class SupabaseStorageProvider(StorageProvider):
    """Supabase Storage over its REST API, with the service-role key.

    The key goes in `Authorization: Bearer` and in the `apikey` header (Supabase checks both) and
    is never written to a log line or a response body.
    """

    def __init__(self, base_url: str, service_key: str, bucket: str):
        self.base_url = base_url.rstrip("/")
        self.bucket = bucket
        self._headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        # `put` extends the auth headers with its own; merging here is what lets it, because
        # `client.request(..., **kwargs)` would otherwise receive `headers` twice.
        headers = {**self._headers, **kwargs.pop("headers", {})}
        last: Exception | None = None
        for attempt in (1, 2):
            try:
                with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
                    response = client.request(method, url, headers=headers, **kwargs)
            except httpx.HTTPError as exc:  # a dropped connection is worth the same single retry
                last = exc
                continue
            if response.status_code < 500:
                return response
            last = httpx.HTTPStatusError(
                f"{response.status_code} from storage", request=response.request, response=response
            )
            if attempt == 2:
                raise last
        raise last  # pragma: no cover - the loop above always returns or raises

    def put(self, path: str, data: bytes, mime: str) -> None:
        response = self._request(
            "POST",
            f"{self.base_url}/storage/v1/object/{self.bucket}/{path}",
            content=data,
            headers={**self._headers, "Content-Type": mime, "x-upsert": "false"},
        )
        if response.status_code >= 400:
            raise AppError(502, "STORAGE_UNAVAILABLE", "Could not store the receipt", {"status": response.status_code})

    def signed_url(self, path: str, expires_in: int) -> str:
        response = self._request(
            "POST",
            f"{self.base_url}/storage/v1/object/sign/{self.bucket}/{path}",
            json={"expiresIn": expires_in},
        )
        if response.status_code >= 400:
            raise AppError(502, "STORAGE_UNAVAILABLE", "Could not sign a receipt URL", {"status": response.status_code})
        signed = response.json().get("signedURL", "")
        if not signed:
            raise AppError(502, "STORAGE_UNAVAILABLE", "Storage returned no signed URL", {})
        # Supabase returns "/object/sign/<bucket>/<path>?token=..." - relative to /storage/v1.
        return f"{self.base_url}/storage/v1{signed}" if signed.startswith("/") else signed

    def delete(self, path: str) -> None:
        self._request("DELETE", f"{self.base_url}/storage/v1/object/{self.bucket}/{path}")


_provider: StorageProvider | None = None


def get_provider() -> StorageProvider:
    """Process-wide, built from settings on first use. `delete` and `put` are best-effort in the
    callers, so a misconfigured provider surfaces as a 502 rather than an import-time crash."""
    global _provider
    if _provider is None:
        bucket = settings.RECEIPTS_BUCKET
        if settings.STORAGE_PROVIDER == "supabase":
            if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
                raise AppError(
                    500,
                    "STORAGE_NOT_CONFIGURED",
                    "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required when STORAGE_PROVIDER=supabase",
                    {},
                )
            _provider = SupabaseStorageProvider(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY, bucket)
        else:
            _provider = LocalStorageProvider(settings.LOCAL_STORAGE_DIR, bucket)
    return _provider


def reset_provider() -> None:
    """For tests and for `scripts/setup_storage.py`, which flips settings at runtime."""
    global _provider
    _provider = None


def signed_receipt_url(path: str) -> str:
    return get_provider().signed_url(path, settings.RECEIPT_URL_TTL_SECONDS)
