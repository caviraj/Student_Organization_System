"""Phase 7: the guarantees that are about the API as a whole rather than about a feature.

Most of this file is one of two shapes. The route audits walk `app.routes` and assert a property
of *every* endpoint, so a route added in a later phase is checked the moment it is registered
instead of when somebody remembers to write a test for it. The rest pin the promises the frontend
handoff (`docs/API_HANDOFF.md`) makes about errors, headers and secrets.

The two allowlists below are the documentation. A new public route that is not added to
`PUBLIC_ALLOWLIST` fails `test_no_route_is_accidentally_public` - which is the point: making a
route public should be a decision someone wrote down, not a forgotten `Depends`.
"""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.deps import get_db
from app.core.routes import iter_api_routes
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Routes any caller may reach with no token at all. `iter_api_routes` cannot tell "public" from
# "protected" - a route with no auth dependency and a route with `get_optional_user` both come
# back without `required_roles` - so the list is kept by hand and checked by the count assertion
# in the test that uses it.
PUBLIC_ALLOWLIST = {
    ("/health", "GET"),
    ("/api/v1/auth/register", "POST"),
    ("/api/v1/auth/login", "POST"),
    ("/api/v1/plans", "GET"),
    ("/api/v1/unsubscribe", "GET"),
    # `get_optional_user`: public, but the answer is personalised when a token happens to be sent.
    ("/api/v1/events", "GET"),
    ("/api/v1/events/{event_id}", "GET"),
    ("/api/v1/announcements", "GET"),
    ("/api/v1/announcements/{announcement_id}", "GET"),
    ("/api/v1/products", "GET"),
    ("/api/v1/products/{product_id}", "GET"),
    # The gateway calls this, not a browser. It carries no token by design: the signature over the
    # raw body is the authentication, and the handler refuses everything else.
    ("/api/v1/payments/webhook", "POST"),
}

# Every authenticated route a plain `member` may reach - both the ones with a `require_role`
# floor at member and the ones that only need a valid token. Everything else that needs a token
# must answer 403 - not 401, not 404 - so the frontend can tell "log in again" from "not your call".
MEMBER_ALLOWED = {
    ("/api/v1/auth/me", "GET"),
    ("/api/v1/auth/permissions", "GET"),
    ("/api/v1/members/me/card", "GET"),
    ("/api/v1/memberships/checkout", "POST"),
    ("/api/v1/memberships/me", "GET"),
    ("/api/v1/payments/{order_id}/mock-confirm", "POST"),
    ("/api/v1/payments/{order_id}", "GET"),
    ("/api/v1/payments/{order_id}/verify", "POST"),
    ("/api/v1/tickets/checkout", "POST"),
    ("/api/v1/tickets/me", "GET"),
    ("/api/v1/tickets/{ticket_id}", "GET"),
    ("/api/v1/orders/merch/checkout", "POST"),
    ("/api/v1/orders/me", "GET"),
    ("/api/v1/orders/{order_id}", "GET"),
    ("/api/v1/users/me/email-preferences", "GET"),
    ("/api/v1/users/me/email-preferences", "POST"),
}

# `{...}` segments: a real path has to go out on the wire or the route never matches.
FAKE_ID = str(uuid4())


def _routes():
    return list(iter_api_routes(app))


def _concrete(path: str) -> str:
    for name in ("event_id", "announcement_id", "product_id", "ticket_id", "order_id", "user_id", "variant_id"):
        path = path.replace(f"{{{name}}}", FAKE_ID)
    return path


def _call(client: TestClient, path: str, method: str, headers: dict | None = None):
    """One request with a method-appropriate, deliberately empty payload.

    An empty body is enough for every audit here: the auth dependency runs before body validation,
    so a protected route answers 401/403 regardless of what was (not) sent, and a body that fails
    validation on an *allowed* route is a 422 we treat as "got past the role check".
    """
    url = _concrete(path)
    kwargs = {"headers": headers or {}}
    if method in ("POST", "PATCH", "PUT"):
        kwargs["json"] = {}
    return client.request(method, url, **kwargs)


# --- the allowlists are the check, so they must match the app ---------------------
def test_route_count_matches_openapi():
    """`iter_api_routes` reaches into FastAPI internals to unwrap `include_router`. If an upgrade
    changes that shape the helper would silently yield nothing, and every audit below would pass
    vacuously. `app.openapi()` is the framework's own view, so the two must agree."""
    operations = sum(len(methods) for methods in app.openapi()["paths"].values())
    assert len(_routes()) == operations
    assert len(_routes()) > 80  # a collapsed helper cannot pass this by returning [] either
    # `get_optional_user` is not `require_role`, so these routes have no `required_roles` either -
    # and the classification is the whole basis of the two allowlists.
    authless = {(path, method) for path, route in _routes() for method in route.methods if not _has_auth(path, route)}
    assert authless == PUBLIC_ALLOWLIST


def _has_auth(path: str, route: APIRoute) -> bool:
    stack = [route.dependant]
    while stack:
        dep = stack.pop()
        name = getattr(dep.call, "__name__", "")
        if name in ("get_current_user", "require_role") or getattr(dep.call, "required_roles", None):
            return True
        stack.extend(dep.dependencies)
    return False


def test_no_route_is_accidentally_public(client):
    """Without a token, every route outside the allowlist is a 401. A new endpoint that forgot its
    `Depends(require_role(...))` fails here rather than in production."""
    for path, route in _routes():
        for method in route.methods:
            if (path, method) in PUBLIC_ALLOWLIST:
                continue
            response = _call(client, path, method)
            assert response.status_code == 401, f"{method} {path} answered {response.status_code} with no token"
            body = response.json()
            assert body["error"]["code"] == "UNAUTHORIZED", f"{method} {path} -> {body}"


def test_public_allowlist_routes_do_not_401(client):
    """The other direction: nothing in the allowlist actually demands a token. Without this, a
    route could be listed as public and still be protected, and the audit above would not notice."""
    for path, method in PUBLIC_ALLOWLIST:
        response = _call(client, path, method)
        assert response.status_code != 401, f"{method} {path} is in PUBLIC_ALLOWLIST but demands a token"


def test_member_role_matrix(client, make_user, login):
    """One member token against every role-gated route. `MEMBER_ALLOWED` is the contract; a route
    that moves up or down the ladder without the list moving with it fails here."""
    make_user("member@ssa.org", role="member")
    headers = {"Authorization": f"Bearer {login('member@ssa.org')}"}

    for path, route in _routes():
        for method in route.methods:
            if (path, method) in PUBLIC_ALLOWLIST or not _has_auth(path, route):
                continue
            response = _call(client, path, method, headers=headers)
            allowed = (path, method) in MEMBER_ALLOWED
            if allowed:
                assert response.status_code != 403, f"{method} {path} refused a member: {response.text}"
            else:
                assert response.status_code == 403, f"{method} {path} let a member through ({response.status_code})"
                assert response.json()["error"]["code"] == "FORBIDDEN"


# --- error shape ------------------------------------------------------------------
def test_validation_error_lists_fields(client):
    # Two independent failures, so the list is a list and not a single banner. `password` is
    # deliberately not one of them: a weak password is `WEAK_PASSWORD` (see below), not
    # `VALIDATION_ERROR`, and mixing the two would make the frontend map a code onto two fields.
    response = client.post(
        "/api/v1/auth/register", json={"email": "not-an-email", "password": "Passw0rd!", "full_name": ""}
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    fields = error["details"]["fields"]
    assert {item["field"] for item in fields} >= {"email", "full_name"}
    assert all(item["message"] for item in fields)


@pytest.mark.parametrize(
    ("method", "url", "code"),
    [
        ("GET", "/api/v1/no-such-thing", "NOT_FOUND"),
        ("GET", "/api/v1/events/" + FAKE_ID + "/ticket-types", "METHOD_NOT_ALLOWED"),
    ],
)
def test_framework_errors_use_the_envelope(client, method, url, code):
    """404 and 405 are raised by Starlette, not by us. They are the two a client hits by accident,
    so they are exactly the two that must not come back as `{"detail": "Not Found"}`."""
    response = client.request(method, url)
    assert response.status_code in (404, 405)
    assert response.json()["error"]["code"] == code


def test_unhandled_error_hides_the_traceback(client, monkeypatch):
    def boom():
        raise RuntimeError("the database exploded: postgres://user:hunter2@host/db")

    app.dependency_overrides[get_db] = boom
    # `TestClient` re-raises by default; the handler still ran and produced the body, so turn the
    # re-raise off and read what the client would actually have received.
    try:
        with TestClient(app, raise_server_exceptions=False) as raw:
            response = raw.get("/api/v1/plans")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 500
    assert response.json() == {"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong", "details": {}}}
    assert "hunter2" not in response.text and "Traceback" not in response.text


# --- headers ----------------------------------------------------------------------
def test_security_headers_and_request_id(client):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Request-ID"]


def test_request_id_is_echoed(client):
    response = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_error_responses_carry_security_headers(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers["X-Content-Type-Options"] == "nosniff"


# --- nothing in the response schema is a secret -----------------------------------
FORBIDDEN_FIELDS = {
    "password",
    "password_hash",
    "hashed_password",
    "storage_path",
    "receipt_path",
    "object_path",
    "supabase_service_role_key",
    "service_role_key",
    "jwt_secret",
    "access_token_hash",
}


def test_no_response_schema_exposes_a_secret_field():
    """The response models are the only thing standing between a `User` row and a
    `password_hash` on the wire. Walk every response schema the app advertises and assert none of
    them names one of these - a new `ORMModel` that forgets `exclude` fails here."""
    import re

    raw = json.dumps(app.openapi())
    # `$ref`s only: an inline property called "password" would be caught by the same name check.
    names = set(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*\{\s*"title"', raw))
    offenders = names & FORBIDDEN_FIELDS
    assert not offenders, f"openapi exposes {sorted(offenders)}"


# --- secrets never reach the log ---------------------------------------------------
def _captured(caplog) -> str:
    """Only this app's own log records.

    `caplog` also catches the *test harness's* loggers, and httpx logs the full URL of every
    request it makes - query string included. That is a property of `TestClient`, not of the
    running server, and asserting on it would be asserting that our tests do not use httpx. The
    logger names that matter are the ones the app configures under `ssa` in `app/main.py`.
    """
    return "\n".join(record.getMessage() for record in caplog.records if record.name.split(".")[0] == "ssa")


def test_login_does_not_log_the_password_or_token(client, make_user, caplog):
    make_user("logme@ssa.org")
    secret = "Passw0rd!TopSecret"

    with caplog.at_level(0):
        response = client.post("/api/v1/auth/login", json={"email": "logme@ssa.org", "password": secret})

    assert response.status_code == 401  # the fixture's password, not this one
    logged = _captured(caplog)
    assert secret not in logged
    assert "Authorization" not in logged
    # The request line exists (so the assertion is not passing because nothing was logged).
    assert "/api/v1/auth/login" in logged


def test_unsubscribe_query_token_does_not_reach_the_log(client, caplog):
    """The unsubscribe link is the one place a real token travels in a query string, and the
    request logger drops the query entirely. If it ever stops doing that, this fails."""
    token = "tok_live_9f3c1a7b2e"
    with caplog.at_level(0):
        response = client.get(f"/api/v1/unsubscribe?token={token}")

    assert response.status_code in (200, 400)
    logged = _captured(caplog)
    assert token not in logged
    assert "/api/v1/unsubscribe" in logged


# --- rate limiting and lockout -----------------------------------------------------
def test_login_is_rate_limited_by_ip(client, rate_limits):
    for _ in range(rate_limits.settings.LOGIN_PER_MINUTE):
        client.post("/api/v1/auth/login", json={"email": "nobody@ssa.org", "password": "Passw0rd!"})

    response = client.post("/api/v1/auth/login", json={"email": "nobody@ssa.org", "password": "Passw0rd!"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "TOO_MANY_REQUESTS"
    assert int(response.headers["Retry-After"]) > 0


def test_five_failed_logins_lock_the_email_out(client, make_user, rate_limits, monkeypatch):
    """`LOGIN_FAILURES_BEFORE_LOCKOUT` consecutive failures lock the *email*, and the lock answers
    even for the correct password - otherwise it is only a speed bump."""
    make_user("locked@ssa.org")
    monkeypatch.setattr(rate_limits.settings, "LOGIN_PER_MINUTE", 1000)  # isolate the lockout from the IP window

    for _ in range(rate_limits.settings.LOGIN_FAILURES_BEFORE_LOCKOUT):
        assert (
            client.post("/api/v1/auth/login", json={"email": "locked@ssa.org", "password": "wrong"}).status_code == 401
        )

    response = client.post("/api/v1/auth/login", json={"email": "locked@ssa.org", "password": "Passw0rd!"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "TOO_MANY_REQUESTS"
    assert int(response.headers["Retry-After"]) > 0


def test_a_successful_login_clears_the_failure_count(client, make_user, rate_limits, monkeypatch):
    """Four failures then a success then four more must not lock: the counter is consecutive
    failures, not failures ever."""
    make_user("reset@ssa.org")
    monkeypatch.setattr(rate_limits.settings, "LOGIN_PER_MINUTE", 1000)
    monkeypatch.setattr(rate_limits.settings, "LOGIN_FAILURES_BEFORE_LOCKOUT", 5)

    for _ in range(4):
        client.post("/api/v1/auth/login", json={"email": "reset@ssa.org", "password": "wrong"})
    assert (
        client.post("/api/v1/auth/login", json={"email": "reset@ssa.org", "password": "Passw0rd!"}).status_code == 200
    )
    for _ in range(4):
        client.post("/api/v1/auth/login", json={"email": "reset@ssa.org", "password": "wrong"})

    assert (
        client.post("/api/v1/auth/login", json={"email": "reset@ssa.org", "password": "Passw0rd!"}).status_code == 200
    )


def test_wrong_password_says_nothing_about_the_account(client, make_user):
    """Same code and same message whether the email exists or not - the response must not be an
    account-existence oracle."""
    make_user("real@ssa.org")
    known = client.post("/api/v1/auth/login", json={"email": "real@ssa.org", "password": "wrong"})
    unknown = client.post("/api/v1/auth/login", json={"email": "ghost@ssa.org", "password": "wrong"})

    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()


def test_checkin_is_rate_limited_per_user(client, make_user, make_event, login, rate_limits):
    """Keyed by user, so one busy scanner cannot lock out the other door. The limit is read from
    settings when the router is imported, so this drives the real 120 rather than a patched one."""
    make_user("scanner@ssa.org", role="volunteer")
    event = make_event()
    headers = {"Authorization": f"Bearer {login('scanner@ssa.org')}"}
    body = {"event_id": str(event.id), "code": "NOPE123456"}

    for _ in range(rate_limits.settings.CHECKIN_PER_MINUTE):
        response = client.post("/api/v1/checkin", json=body, headers=headers)
        assert response.status_code == 200  # a bad code is a 200 with result=INVALID, not an error

    response = client.post("/api/v1/checkin", json=body, headers=headers)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "TOO_MANY_REQUESTS"
    assert int(response.headers["Retry-After"]) > 0


def test_checkin_limit_is_per_user_and_not_per_server(client, make_user, make_event, login, rate_limits):
    """A second volunteer still gets through after the first one has spent the whole budget."""
    make_user("scanner-a@ssa.org", role="volunteer")
    make_user("scanner-b@ssa.org", role="volunteer")
    event = make_event()
    body = {"event_id": str(event.id), "code": "NOPE123456"}
    a = {"Authorization": f"Bearer {login('scanner-a@ssa.org')}"}
    b = {"Authorization": f"Bearer {login('scanner-b@ssa.org')}"}

    for _ in range(rate_limits.settings.CHECKIN_PER_MINUTE):
        client.post("/api/v1/checkin", json=body, headers=a)

    assert client.post("/api/v1/checkin", json=body, headers=a).status_code == 429
    assert client.post("/api/v1/checkin", json=body, headers=b).status_code == 200


# --- password policy ---------------------------------------------------------------
@pytest.mark.parametrize("password", ["short1", "allletters", "12345678"])
def test_weak_passwords_are_rejected(client, password):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"weak-{uuid4().hex[:8]}@ssa.org", "password": password, "full_name": "Weak"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "WEAK_PASSWORD"


def test_a_strong_password_registers(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"strong-{uuid4().hex[:8]}@ssa.org", "password": "Passw0rd!", "full_name": "Strong"},
    )
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "guest"
    assert response.json()["user"]["member_code"] is None


# --- CORS --------------------------------------------------------------------------
def test_cors_allows_the_vite_dev_origin(client):
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_does_not_allow_an_unknown_origin(client):
    response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert response.headers.get("access-control-allow-origin") is None
