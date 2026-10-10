"""Register / login / me and the role guards (FR-1.1, PRD §3)."""

from app.models import User

REGISTER = {
    "email": "new.student@ssa.org",
    "password": "Passw0rd!",
    "full_name": "New Student",
    "phone": "9876543210",
    "department": "CSE",
    "year": 2,
}


def test_register_returns_user_and_token(client):
    response = client.post("/api/v1/auth/register", json=REGISTER)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["role"] == "guest"  # promoted only after dues are paid
    assert body["user"]["email"] == REGISTER["email"]
    assert "password" not in body["user"] and "password_hash" not in body["user"]


def test_register_rejects_duplicate_email(client):
    client.post("/api/v1/auth/register", json=REGISTER)
    again = client.post("/api/v1/auth/register", json=REGISTER)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "EMAIL_TAKEN"


def test_register_rejects_short_password(client):
    """`WEAK_PASSWORD`, not `VALIDATION_ERROR`: the rule is the club's, it has its own code, and the
    frontend shows it next to the password field. The schema deliberately carries no `min_length`,
    so this is the service's answer and not pydantic's."""
    response = client.post("/api/v1/auth/register", json={**REGISTER, "password": "short"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "WEAK_PASSWORD"


def test_register_rejects_a_password_without_a_digit(client):
    response = client.post("/api/v1/auth/register", json={**REGISTER, "password": "onlyletters"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "WEAK_PASSWORD"


def test_password_is_hashed_not_stored(client, db):
    client.post("/api/v1/auth/register", json=REGISTER)
    user = db.query(User).filter_by(email=REGISTER["email"]).one()
    assert user.password_hash != REGISTER["password"]
    assert user.password_hash.startswith("$2b$")


def test_login_and_me(client):
    client.post("/api/v1/auth/register", json=REGISTER)
    login = client.post("/api/v1/auth/login", json={"email": REGISTER["email"], "password": REGISTER["password"]})
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == REGISTER["email"]
    assert body["membership"] == {"status": "none", "plan_name": None, "end_date": None, "days_left": None}


def test_login_wrong_password_is_401(client):
    client.post("/api/v1/auth/register", json=REGISTER)
    response = client.post("/api/v1/auth/login", json={"email": REGISTER["email"], "password": "WrongPass1!"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_unknown_email_gives_same_error_as_wrong_password(client):
    response = client.post("/api/v1/auth/login", json={"email": "nobody@ssa.org", "password": "Passw0rd!"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_without_token_is_401(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_with_garbage_token_is_401(client):
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401


# --- role guards ------------------------------------------------------------------
def test_member_cannot_reach_admin_routes(client, make_user, login, auth):
    make_user("member@ssa.org", role="member")
    token = login("member@ssa.org")
    for method, path in [
        ("get", "/api/v1/users"),
        ("get", "/api/v1/memberships"),
        ("get", "/api/v1/memberships/renewals-due"),
    ]:
        response = getattr(client, method)(path, headers=auth(token))
        assert response.status_code == 403, f"{path} should be admin-only"
        assert response.json()["error"]["code"] == "FORBIDDEN"


def test_member_cannot_create_plan(client, make_user, login, auth):
    make_user("member@ssa.org", role="member")
    token = login("member@ssa.org")
    response = client.post("/api/v1/plans", json={"name": "Sneaky", "price": 1}, headers=auth(token))
    assert response.status_code == 403


def test_volunteer_cannot_verify_own_role_upgrade(client, make_user, login, auth, db):
    make_user("volunteer@ssa.org", role="volunteer")
    token = login("volunteer@ssa.org")
    target = db.query(User).filter_by(email="volunteer@ssa.org").one()
    response = client.patch(f"/api/v1/users/{target.id}/role", json={"role": "admin"}, headers=auth(token))
    assert response.status_code == 403


def test_role_hierarchy_allows_volunteer_and_above_to_verify(client, make_user, login, auth):
    # volunteer can verify; member cannot (hierarchy admin > treasurer > organizer > volunteer > member > guest)
    make_user("vol@ssa.org", role="volunteer")
    make_user("org@ssa.org", role="organizer")
    make_user("mem@ssa.org", role="member")

    assert (
        client.get("/api/v1/members/verify?code=SSA-2026-9999", headers=auth(login("vol@ssa.org"))).status_code == 200
    )
    assert (
        client.get("/api/v1/members/verify?code=SSA-2026-9999", headers=auth(login("org@ssa.org"))).status_code == 200
    )
    denied = client.get("/api/v1/members/verify?code=SSA-2026-9999", headers=auth(login("mem@ssa.org")))
    assert denied.status_code == 403


def test_admin_can_change_role(client, make_user, login, auth, db):
    make_user("admin@ssa.org", role="admin")
    target = make_user("promote.me@ssa.org", role="guest")
    token = login("admin@ssa.org")
    response = client.patch(f"/api/v1/users/{target.id}/role", json={"role": "organizer"}, headers=auth(token))
    assert response.status_code == 200
    assert response.json()["role"] == "organizer"


def test_admin_can_search_users(client, make_user, login, auth):
    make_user("admin@ssa.org", role="admin")
    make_user("priya.sharma@ssa.org", role="member", full_name="Priya Sharma")
    make_user("rahul.verma@ssa.org", role="member", full_name="Rahul Verma")
    token = login("admin@ssa.org")

    listing = client.get("/api/v1/users", headers=auth(token))
    assert listing.status_code == 200
    assert listing.json()["total"] == 3

    searched = client.get("/api/v1/users?q=Priya", headers=auth(token))
    assert searched.json()["total"] == 1
    assert searched.json()["items"][0]["full_name"] == "Priya Sharma"

    filtered = client.get("/api/v1/users?role=admin", headers=auth(token))
    assert filtered.json()["total"] == 1
