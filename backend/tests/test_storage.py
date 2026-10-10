"""The Supabase Storage provider — the one code path that carries the service-role key.

The test settings use `STORAGE_PROVIDER=local`, so without this file the URLs, the auth headers and
the error mapping of the real provider would ship unexercised. They are stubbed rather than mocked
away: the point is to pin the exact request Supabase receives and the exact error the caller gets.
"""

import httpx
import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.services import storage

KEY = "service-role-key-that-must-never-appear-in-a-response"


class _Stub:
    """A stand-in for httpx.Client that records calls and replays a scripted queue."""

    def __init__(self, queue: list):
        self.queue = queue
        self.calls: list[dict] = []

    def __call__(self, **_kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _provider(monkeypatch, *responses) -> tuple[storage.SupabaseStorageProvider, _Stub]:
    stub = _Stub(list(responses))
    monkeypatch.setattr(storage.httpx, "Client", stub)
    return storage.SupabaseStorageProvider("https://proj.supabase.co/", KEY, "receipts"), stub


def test_put_sends_the_path_we_built_and_both_auth_headers(monkeypatch):
    provider, stub = _provider(monkeypatch, httpx.Response(200, json={}))
    provider.put("2026/abc/def.png", b"\x89PNG", "image/png")

    call = stub.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://proj.supabase.co/storage/v1/object/receipts/2026/abc/def.png"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"  # Supabase checks both headers
    assert call["headers"]["apikey"] == KEY
    assert call["headers"]["x-upsert"] == "false"  # never overwrite somebody else's receipt
    assert call["content"] == b"\x89PNG"


def test_a_relative_signed_url_is_rooted_at_storage_v1(monkeypatch):
    provider, _ = _provider(monkeypatch, httpx.Response(200, json={"signedURL": "/object/sign/receipts/a.png?token=t"}))
    assert provider.signed_url("a.png", 600) == "https://proj.supabase.co/storage/v1/object/sign/receipts/a.png?token=t"


def test_an_absolute_signed_url_is_left_alone(monkeypatch):
    absolute = "https://proj.supabase.co/storage/v1/object/sign/receipts/a.png?token=t"
    provider, _ = _provider(monkeypatch, httpx.Response(200, json={"signedURL": absolute}))
    assert provider.signed_url("a.png", 600) == absolute


def test_a_signed_url_without_a_token_is_a_502(monkeypatch):
    provider, _ = _provider(monkeypatch, httpx.Response(200, json={}))
    with pytest.raises(AppError) as caught:
        provider.signed_url("a.png", 600)
    assert caught.value.status_code == 502
    assert caught.value.code == "STORAGE_UNAVAILABLE"


def test_a_4xx_is_not_retried_and_becomes_a_502_without_the_key(monkeypatch):
    provider, stub = _provider(monkeypatch, httpx.Response(400, json={"message": "nope"}))
    with pytest.raises(AppError) as caught:
        provider.put("a.png", b"x", "image/png")

    assert len(stub.calls) == 1
    assert caught.value.status_code == 502
    assert caught.value.code == "STORAGE_UNAVAILABLE"
    assert KEY not in str(caught.value.details)  # the key is in the headers, never in the error


def test_a_dropped_connection_is_retried_once(monkeypatch):
    provider, stub = _provider(monkeypatch, httpx.ConnectError("dropped"), httpx.Response(200, json={}))
    provider.put("a.png", b"x", "image/png")
    assert len(stub.calls) == 2  # a transient 502 should not lose a volunteer's receipt


def test_a_5xx_is_retried_once_and_then_surfaces(monkeypatch):
    # A real response carries the request that produced it; the provider reads `response.request`
    # when it wraps the failure, so the stub has to as well.
    request = httpx.Request("POST", "https://proj.supabase.co/storage/v1/object/receipts/a.png")
    provider, stub = _provider(monkeypatch, httpx.Response(503, request=request), httpx.Response(503, request=request))
    with pytest.raises(httpx.HTTPStatusError):
        provider.put("a.png", b"x", "image/png")
    assert len(stub.calls) == 2


def test_a_missing_key_is_a_config_error_not_an_import_error(monkeypatch):
    monkeypatch.setattr(storage, "_provider", None)
    monkeypatch.setattr(settings, "STORAGE_PROVIDER", "supabase")
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "")

    with pytest.raises(AppError) as caught:
        storage.get_provider()
    assert caught.value.code == "STORAGE_NOT_CONFIGURED"
