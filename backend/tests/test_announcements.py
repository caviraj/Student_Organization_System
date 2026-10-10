"""Phase 3: who sees an announcement, who gets it, what an edit is allowed to change, and the
mailing-list worker (DESIGN.md §4 rule 10, PRD FR-3.1-3.3).

Posts made through the API kick the worker as a background task, so the tests that need to watch
the queue use `post_direct` (the same service, no kick) and drive the worker by hand.
"""

import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.db import duplicate_database_reason
from app.core.security import ALGORITHM
from app.models import (
    Announcement,
    AnnouncementDelivery,
    AnnouncementRevision,
    Membership,
    Ticket,
    User,
)
from app.services import announcements as service
from app.services import delivery_worker as worker  # patched: swaps the email provider
from app.services.delivery_worker import MAX_ATTEMPTS, process_queued_deliveries
from app.services.mailer import FAILURE_DOMAIN, EmailProvider
from app.services.unsubscribe import create_unsubscribe_token
from tests.conftest import TestingSession, buy_tickets

PUBLIC = {"title": "Club desk open", "body": "Open all week.", "category": "general", "audience": "all"}
MEMBERS_ONLY = {
    "title": "Members' AGM next Friday",
    "body": "4 PM in the Seminar Hall.",
    "category": "deadline",
    "audience": "members",
}
EVENT_POST = {
    "title": "Spring Gala: doors open 6 PM",
    "body": "Bring your QR ticket.",
    "category": "change",
    "audience": "event",
}


def _code(response) -> str:
    return response.json()["error"]["code"]


def titles(response) -> list[str]:
    return [item["title"] for item in response.json()["items"]]


def post(client, auth, token, **overrides) -> dict:
    response = client.post(
        "/api/v1/announcements",
        json={"title": "T", "body": "B", "category": "general"} | overrides,
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def post_direct(db, author, **overrides) -> tuple[Announcement, dict]:
    """The same service the endpoint calls, without the background kick."""
    payload = {"title": "T", "body": "B", "category": "general", "audience": "all"} | overrides
    result = service.create_announcement(db, author, payload)
    return result["announcement"], result["delivery_summary"]


def deliveries(db, announcement_id) -> list[AnnouncementDelivery]:
    db.expire_all()
    return list(
        db.scalars(
            select(AnnouncementDelivery).where(
                AnnouncementDelivery.announcement_id == UUID(str(announcement_id))
            )
        )
    )


class CountingProvider(EmailProvider):
    """Records what would have gone out, and can be told to block mid-send."""

    def __init__(self, block: threading.Event | None = None, release: threading.Event | None = None):
        self.sent: list[str] = []
        self._block = block
        self._release = release

    def send(self, to_email: str, subject: str, html: str, text: str) -> None:
        if self._block is not None:
            self._block.set()
            assert self._release.wait(timeout=20), "worker was never released"
        self.sent.append(to_email)


@pytest.fixture
def organizer(make_user, login):
    make_user("organizer@ssa.org", role="organizer", full_name="Om Prakash")
    return login("organizer@ssa.org")


@pytest.fixture
def organizer_user(make_user):
    return make_user("organizer@ssa.org", role="organizer", full_name="Om Prakash")


@pytest.fixture
def admin(make_user, login):
    make_user("admin@ssa.org", role="admin", full_name="Aarav Menon")
    return login("admin@ssa.org")


@pytest.fixture
def member(make_user, login):
    make_user("member@ssa.org", role="member", full_name="Meera Member")
    return login("member@ssa.org")


@pytest.fixture
def staff(db, make_user, make_membership):
    """Two members: one reachable, one whose address always bounces."""
    make_user("one@ssa.org", full_name="One Member")
    make_membership(db.scalar(select(User).where(User.email == "one@ssa.org")))
    bounce = make_user(f"two@{FAILURE_DOMAIN}", full_name="Two Member")
    make_membership(bounce)
    return db.scalar(select(User).where(User.email == "one@ssa.org")), bounce


# --- 1. the test database guard ---------------------------------------------------
def test_guard_refuses_when_test_and_app_urls_share_a_database():
    assert duplicate_database_reason(None, "postgresql+psycopg://u@host:5432/postgres")
    reason = duplicate_database_reason(
        "postgresql+psycopg://u@host:5432/postgres", "postgresql+psycopg://u@host:6543/postgres"
    )
    assert reason and "same database" in reason
    # Same host, different database name: that IS the safe setup, so it must not be blocked.
    assert (
        duplicate_database_reason(
            "postgresql+psycopg://u@host:5432/ssa_hub_test", "postgresql+psycopg://u@host:6543/postgres"
        )
        is None
    )


def test_this_suite_is_not_pointed_at_the_app_database():
    assert settings.TEST_DATABASE_URL, "conftest would have aborted without it"
    assert duplicate_database_reason(settings.TEST_DATABASE_URL, settings.DATABASE_URL) is None


# --- 2. visibility matrix ---------------------------------------------------------
@pytest.fixture
def world(client, db, auth, login, make_user, make_membership, make_event, make_ticket_type):
    """An event, a ticket holder, a holder whose ticket is used, and one whose ticket is void."""
    event = make_event(title="Spring Gala")
    ticket_type = make_ticket_type(event, capacity=10)

    make_membership(make_user("active@ssa.org"))  # member + live dues
    make_membership(make_user("lapsed@ssa.org"), status="expired", days_left=-30)
    make_user("outsider@ssa.org")  # role member, never paid
    make_user("holder@ssa.org")
    make_user("used@ssa.org")
    make_user("voided@ssa.org")

    bought = buy_tickets(client, auth, login("holder@ssa.org"), ticket_type.id, quantity=1)
    assert bought["tickets"], bought
    used = buy_tickets(client, auth, login("used@ssa.org"), ticket_type.id, quantity=1)
    db.get(Ticket, UUID(used["tickets"][0]["id"])).status = "used"
    void = buy_tickets(client, auth, login("voided@ssa.org"), ticket_type.id, quantity=1)
    db.get(Ticket, UUID(void["tickets"][0]["id"])).status = "void"
    db.commit()
    return event


def test_feed_visibility_matrix(client, db, auth, login, world, organizer, admin):
    public = post(client, auth, organizer, **PUBLIC)
    members = post(client, auth, organizer, **MEMBERS_ONLY)
    post(client, auth, organizer, **EVENT_POST, event_id=str(world.id))

    anonymous = client.get("/api/v1/announcements")
    assert anonymous.status_code == 200
    assert titles(anonymous) == [PUBLIC["title"]]

    active = client.get("/api/v1/announcements", headers=auth(login("active@ssa.org")))
    assert set(titles(active)) == {PUBLIC["title"], MEMBERS_ONLY["title"]}

    lapsed = client.get("/api/v1/announcements", headers=auth(login("lapsed@ssa.org")))
    assert titles(lapsed) == [PUBLIC["title"]], "expired dues do not unlock members-only posts"

    outsider = client.get("/api/v1/announcements", headers=auth(login("outsider@ssa.org")))
    assert titles(outsider) == [PUBLIC["title"]], "a signed-in non-member is not a member"

    holder = client.get("/api/v1/announcements", headers=auth(login("holder@ssa.org")))
    assert set(titles(holder)) == {PUBLIC["title"], EVENT_POST["title"]}

    used = client.get("/api/v1/announcements", headers=auth(login("used@ssa.org")))
    assert set(titles(used)) == {PUBLIC["title"], EVENT_POST["title"]}, "a used ticket still counts"

    voided = client.get("/api/v1/announcements", headers=auth(login("voided@ssa.org")))
    assert titles(voided) == [PUBLIC["title"]], "a void ticket is not an invitation"

    staff_view = client.get("/api/v1/announcements", headers=auth(organizer))
    assert set(titles(staff_view)) == {PUBLIC["title"], MEMBERS_ONLY["title"], EVENT_POST["title"]}

    admin_view = client.get("/api/v1/announcements", headers=auth(admin))
    assert len(titles(admin_view)) == 3, "admin outranks organizer"

    # A post you may not see is a 404, never a 403: its existence is itself members-only news.
    assert client.get(f"/api/v1/announcements/{members['id']}").status_code == 404
    assert (
        client.get(f"/api/v1/announcements/{members['id']}", headers=auth(login("active@ssa.org"))).status_code
        == 200
    )
    assert client.get(f"/api/v1/announcements/{uuid4()}").status_code == 404

    detail = client.get(f"/api/v1/announcements/{public['id']}").json()
    assert detail["body"] == PUBLIC["body"], "the detail endpoint returns the whole body"
    assert detail["edited_at"] is None
    assert detail["author_name"] == "Om Prakash"


# --- 3. ordering and pinning ------------------------------------------------------
def test_feed_is_pinned_first_then_newest(client, db, auth, organizer):
    old = post(client, auth, organizer, **(PUBLIC | {"title": "Old"}))
    new = post(client, auth, organizer, **(PUBLIC | {"title": "New"}))
    pinned = post(client, auth, organizer, **(PUBLIC | {"title": "Pinned", "is_pinned": True}))

    base = datetime.now(UTC)
    db.get(Announcement, UUID(old["id"])).published_at = base - timedelta(days=5)
    db.get(Announcement, UUID(new["id"])).published_at = base
    db.get(Announcement, UUID(pinned["id"])).published_at = base - timedelta(days=30)
    db.commit()

    feed = client.get("/api/v1/announcements")
    assert titles(feed) == ["Pinned", "New", "Old"]
    assert feed.json()["total"] == 3

    assert titles(client.get("/api/v1/announcements", params={"pinned": True})) == ["Pinned"]
    assert titles(client.get("/api/v1/announcements", params={"pinned": False})) == ["New", "Old"]
    assert titles(client.get("/api/v1/announcements", params={"category": "general"})) == [
        "Pinned",
        "New",
        "Old",
    ]
    assert titles(client.get("/api/v1/announcements", params={"category": "meeting"})) == []
    assert titles(client.get("/api/v1/announcements", params={"q": "new"})) == ["New"]

    page = client.get("/api/v1/announcements", params={"page": 2, "page_size": 2})
    assert titles(page) == ["Old"] and page.json()["total"] == 3


def test_at_most_three_pinned(client, db, auth, organizer):
    for index in range(3):
        post(client, auth, organizer, **(PUBLIC | {"title": f"Pin {index}", "is_pinned": True}))

    fourth = client.post(
        "/api/v1/announcements",
        json=PUBLIC | {"title": "Pin 4", "is_pinned": True},
        headers=auth(organizer),
    )
    assert fourth.status_code == 409, fourth.text
    assert _code(fourth) == "PIN_LIMIT_REACHED"

    # Unpinning one makes room again: the limit is a live count, not a one-way door.
    top = client.get("/api/v1/announcements", params={"pinned": True}).json()["items"][0]
    assert client.patch(
        f"/api/v1/announcements/{top['id']}", json={"is_pinned": False}, headers=auth(organizer)
    ).status_code == 200
    post(client, auth, organizer, **(PUBLIC | {"title": "Pin 4", "is_pinned": True}))


def test_body_preview_is_the_first_200_characters(client, auth, organizer):
    body = "x" * 500
    created = post(client, auth, organizer, **(PUBLIC | {"body": body}))
    assert created["body"] == body
    item = client.get("/api/v1/announcements").json()["items"][0]
    assert item["body_preview"] == body[:200]
    assert "body" not in item


# --- 4. recipients ----------------------------------------------------------------
def test_recipients_are_resolved_from_the_audience(db, make_user, make_membership, organizer_user):
    make_membership(make_user("member@ssa.org"))
    make_membership(make_user("lapsed@ssa.org"), status="expired", days_left=-5)
    make_user("outsider@ssa.org")
    make_membership(make_user("quiet@ssa.org", email_opt_in=False))
    make_user("gone@ssa.org", is_active=False)

    # Members-only: exactly the two live memberships, and the opted-out one gets no email.
    _, summary = post_direct(db, organizer_user, **MEMBERS_ONLY, send_email=True)
    assert summary == {"inapp_queued": 2, "email_queued": 1, "skipped_opted_out": 1}

    # Everyone active: 5 users (the author and four members), one of them opted out.
    announcement, everyone = post_direct(db, organizer_user, **PUBLIC, send_email=True)
    assert everyone == {"inapp_queued": 5, "email_queued": 4, "skipped_opted_out": 1}
    rows = deliveries(db, announcement.id)
    assert len(rows) == 9
    quiet_user = db.scalar(select(User).where(User.email == "quiet@ssa.org"))
    opted_in = set(
        db.scalars(select(User.id).where(User.is_active.is_(True), User.email_opt_in.is_(True)))
    )
    assert {r.user_id for r in rows if r.channel == "email"} == opted_in, "opted-out users get no email"
    assert quiet_user.id not in {r.user_id for r in rows if r.channel == "email"}
    assert len({r.user_id for r in rows if r.channel == "inapp"}) == 5
    assert all(r.status == "queued" and r.attempts == 0 for r in rows)

    # send_email=false: no email rows at all, opted out or not.
    quiet, quiet_summary = post_direct(db, organizer_user, **PUBLIC)
    assert quiet_summary == {"inapp_queued": 5, "email_queued": 0, "skipped_opted_out": 0}
    assert {r.channel for r in deliveries(db, quiet.id)} == {"inapp"}


def test_event_audience_is_the_ticket_holders(client, db, auth, login, make_user, make_event, make_ticket_type, organizer_user):
    event = make_event()
    ticket_type = make_ticket_type(event, capacity=5)
    make_user("holder@ssa.org")
    make_user("bystander@ssa.org")
    bought = buy_tickets(client, auth, login("holder@ssa.org"), ticket_type.id, quantity=2)
    assert bought["tickets"]

    announcement, summary = post_direct(
        db, organizer_user, **EVENT_POST, event_id=event.id, send_email=True
    )
    assert summary["inapp_queued"] == 1, "one holder, however many tickets they hold"
    holder = db.scalar(select(User).where(User.email == "holder@ssa.org"))
    assert {r.user_id for r in deliveries(db, announcement.id)} == {holder.id}


def test_event_audience_needs_an_event_id(client, auth, organizer, make_event):
    missing = client.post("/api/v1/announcements", json=EVENT_POST, headers=auth(organizer))
    assert missing.status_code == 422 and _code(missing) == "EVENT_REQUIRED"

    unknown = client.post(
        "/api/v1/announcements",
        json=EVENT_POST | {"event_id": str(uuid4())},
        headers=auth(organizer),
    )
    assert unknown.status_code == 404 and _code(unknown) == "EVENT_NOT_FOUND"

    stray = client.post(
        "/api/v1/announcements",
        json=PUBLIC | {"event_id": str(make_event().id)},
        headers=auth(organizer),
    )
    assert stray.status_code == 422 and _code(stray) == "EVENT_NOT_ALLOWED"


def test_a_recipient_cannot_be_queued_twice(db, make_user, make_membership, organizer_user):
    make_membership(make_user("member@ssa.org"))
    announcement, _ = post_direct(db, organizer_user, **MEMBERS_ONLY, send_email=True)
    existing = deliveries(db, announcement.id)[0]

    db.add(
        AnnouncementDelivery(
            announcement_id=existing.announcement_id,
            user_id=existing.user_id,
            channel=existing.channel,
            status="queued",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# --- 5. the delivery worker -------------------------------------------------------
def test_worker_sends_queued_rows_once(db, monkeypatch, make_user, make_membership, organizer_user):
    make_membership(make_user("member@ssa.org"))
    announcement, summary = post_direct(db, organizer_user, **MEMBERS_ONLY, send_email=True)
    assert summary == {"inapp_queued": 1, "email_queued": 1, "skipped_opted_out": 0}

    provider = CountingProvider()
    monkeypatch.setattr(worker, "get_provider", lambda: provider)

    assert process_queued_deliveries(db) == {"claimed": 2, "sent": 2, "failed": 0, "retrying": 0}
    assert provider.sent == ["member@ssa.org"]
    rows = deliveries(db, announcement.id)
    assert {r.status for r in rows} == {"sent"}
    assert all(r.sent_at is not None and r.error is None for r in rows)

    # Idempotent: a second pass finds nothing left, so nobody is mailed twice.
    assert process_queued_deliveries(db) == {"claimed": 0, "sent": 0, "failed": 0, "retrying": 0}
    assert provider.sent == ["member@ssa.org"]


def test_failing_address_retries_then_gives_up(db, make_user, make_membership, organizer_user):
    make_membership(make_user(f"nobody@{FAILURE_DOMAIN}"))
    announcement, _ = post_direct(db, organizer_user, **MEMBERS_ONLY, send_email=True)
    email_row = next(r for r in deliveries(db, announcement.id) if r.channel == "email")

    for attempt in range(1, MAX_ATTEMPTS):
        assert process_queued_deliveries(db)["retrying"] == 1
        row = db.get(AnnouncementDelivery, email_row.id)
        assert (row.status, row.attempts) == ("queued", attempt), "stays queued for the next tick"
        assert row.error and FAILURE_DOMAIN in row.error

    assert process_queued_deliveries(db)["failed"] == 1
    row = db.get(AnnouncementDelivery, email_row.id)
    assert (row.status, row.attempts, row.sent_at) == ("failed", MAX_ATTEMPTS, None)

    # The in-app row for that same recipient went out on the first pass: one bad address does not
    # hold up the feed.
    inapp = next(r for r in deliveries(db, announcement.id) if r.channel == "inapp")
    assert db.get(AnnouncementDelivery, inapp.id).status == "sent"
    assert process_queued_deliveries(db) == {"claimed": 0, "sent": 0, "failed": 0, "retrying": 0}


def test_two_workers_never_claim_the_same_row(pg_engine, db, monkeypatch, make_user, make_membership, organizer_user):
    """SKIP LOCKED, proven with a second real connection: while one worker is mid-send (rows
    locked), the other finds nothing to do rather than sending the same mail twice."""
    make_membership(make_user("member@ssa.org"))
    announcement, _ = post_direct(db, organizer_user, **MEMBERS_ONLY, send_email=True)

    started, release = threading.Event(), threading.Event()
    provider = CountingProvider(block=started, release=release)
    monkeypatch.setattr(worker, "get_provider", lambda: provider)

    outcome = {}

    def run_first():
        session = TestingSession()
        try:
            outcome["first"] = process_queued_deliveries(session)
        finally:
            session.close()

    thread = threading.Thread(target=run_first)
    thread.start()
    try:
        assert started.wait(timeout=20), "the first worker never started sending"

        second = TestingSession()
        try:
            outcome["second"] = process_queued_deliveries(second)
        finally:
            second.close()
    finally:
        release.set()
        thread.join(timeout=30)

    assert outcome["first"] == {"claimed": 2, "sent": 2, "failed": 0, "retrying": 0}
    assert outcome["second"] == {"claimed": 0, "sent": 0, "failed": 0, "retrying": 0}
    assert provider.sent == ["member@ssa.org"]
    assert {r.status for r in deliveries(db, announcement.id)} == {"sent"}


def test_posting_kicks_the_worker_so_mail_goes_out_at_once(client, db, auth, member, organizer, make_user, make_membership):
    """The BackgroundTasks hook on POST /announcements. conftest points it at the test session."""
    make_membership(db.scalar(select(User).where(User.email == "member@ssa.org")))
    created = post(client, auth, organizer, **MEMBERS_ONLY, send_email=True)
    assert created["delivery_summary"] == {
        "inapp_queued": 1,
        "email_queued": 1,
        "skipped_opted_out": 0,
    }, "the summary is a queue count, taken before the worker runs"
    assert {r.status for r in deliveries(db, created["id"])} == {"sent"}, "the kick ran first"


# --- 6. edits and revisions -------------------------------------------------------
def test_edit_requires_a_note_and_stores_the_previous_version(client, db, auth, organizer):
    created = post(client, auth, organizer, **PUBLIC)

    refused = client.patch(
        f"/api/v1/announcements/{created['id']}", json={"title": "New title"}, headers=auth(organizer)
    )
    assert refused.status_code == 422 and _code(refused) == "REVISION_NOTE_REQUIRED"
    too_short = client.patch(
        f"/api/v1/announcements/{created['id']}",
        json={"title": "New title", "revision_note": "ty"},
        headers=auth(organizer),
    )
    assert too_short.status_code == 422
    assert db.get(Announcement, UUID(created["id"])).title == PUBLIC["title"]

    edited = client.patch(
        f"/api/v1/announcements/{created['id']}",
        json={"title": "New title", "revision_note": "Fixing the headline"},
        headers=auth(organizer),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "New title"
    assert edited.json()["edited_at"] is not None
    assert edited.json()["revision_note"] == "Fixing the headline"

    revision = db.scalar(select(AnnouncementRevision))
    assert revision.title == PUBLIC["title"], "the row holds the version that was REPLACED"
    assert revision.body == PUBLIC["body"]
    assert revision.note == "Fixing the headline"
    assert revision.edited_by == db.scalar(select(User.id).where(User.email == "organizer@ssa.org"))

    # Nothing actually changed: no note needed, and no revision row invented.
    noop = client.patch(
        f"/api/v1/announcements/{created['id']}", json={"title": "New title"}, headers=auth(organizer)
    )
    assert noop.status_code == 200
    assert db.scalar(select(func.count()).select_from(AnnouncementRevision)) == 1


def test_audience_and_event_are_locked_after_posting(client, auth, organizer, make_event):
    created = post(client, auth, organizer, **EVENT_POST, event_id=str(make_event().id))

    for payload in (
        {"audience": "all", "revision_note": "widen it"},
        {"event_id": str(uuid4()), "revision_note": "wrong event"},
    ):
        response = client.patch(
            f"/api/v1/announcements/{created['id']}", json=payload, headers=auth(organizer)
        )
        assert response.status_code == 422, response.text
        assert _code(response) == "AUDIENCE_LOCKED"

    # Sending the same value is not a change, so it stays a no-op rather than an error.
    same = client.patch(
        f"/api/v1/announcements/{created['id']}", json={"audience": "event"}, headers=auth(organizer)
    )
    assert same.status_code == 200 and same.json()["audience"] == "event"


def test_pinning_needs_no_note_and_revisions_read_newest_first(client, db, auth, organizer):
    created = post(client, auth, organizer, **PUBLIC)

    assert client.patch(
        f"/api/v1/announcements/{created['id']}", json={"is_pinned": True}, headers=auth(organizer)
    ).status_code == 200
    assert db.scalar(select(func.count()).select_from(AnnouncementRevision)) == 0

    for body, note in (("Second version", "First fix"), ("Third version", "Second fix")):
        response = client.patch(
            f"/api/v1/announcements/{created['id']}",
            json={"body": body, "revision_note": note},
            headers=auth(organizer),
        )
        assert response.status_code == 200, response.text

    history = client.get(f"/api/v1/announcements/{created['id']}/revisions", headers=auth(organizer))
    assert history.status_code == 200, history.text
    items = history.json()["items"]
    assert history.json()["total"] == 2
    assert [item["note"] for item in items] == ["Second fix", "First fix"]
    assert items[0]["body"] == "Second version"
    assert items[1]["body"] == PUBLIC["body"], "the oldest revision is the original text"
    assert all(item["edited_by_name"] == "Om Prakash" for item in items)

    assert (
        client.get(f"/api/v1/announcements/{uuid4()}/revisions", headers=auth(organizer)).status_code
        == 404
    )


# --- 7. role guards ---------------------------------------------------------------
def test_role_guards(client, auth, organizer, member, admin):
    created = post(client, auth, organizer, **PUBLIC)

    assert client.post("/api/v1/announcements", json=PUBLIC).status_code == 401

    write = client.post("/api/v1/announcements", json=PUBLIC, headers=auth(member))
    assert write.status_code == 403 and _code(write) == "FORBIDDEN"
    assert (
        client.patch(
            f"/api/v1/announcements/{created['id']}", json={"is_pinned": True}, headers=auth(member)
        ).status_code
        == 403
    )
    assert (
        client.get(f"/api/v1/announcements/{created['id']}/revisions", headers=auth(member)).status_code
        == 403
    ), "the edit history is not member reading"

    # Deliveries name every recipient and their address: admin only.
    deliveries_url = f"/api/v1/announcements/{created['id']}/deliveries"
    assert client.get(deliveries_url).status_code == 401
    assert client.get(deliveries_url, headers=auth(member)).status_code == 403
    assert client.get(deliveries_url, headers=auth(organizer)).status_code == 403
    assert client.get(deliveries_url, headers=auth(admin)).status_code == 200


def test_deliveries_view_reports_per_recipient_status(client, db, auth, admin, organizer, staff):
    created = post(client, auth, organizer, **MEMBERS_ONLY, send_email=True)

    process_queued_deliveries(db)  # one reachable address, one that will bounce
    for _ in range(MAX_ATTEMPTS):
        process_queued_deliveries(db)

    # The audience is members, so the recipients are the live memberships, not every active user.
    recipients = db.scalar(
        select(func.count()).select_from(Membership).where(Membership.status == "active")
    )
    body = client.get(
        f"/api/v1/announcements/{created['id']}/deliveries", headers=auth(admin)
    ).json()
    assert body["summary"] == {
        "email": {"queued": 0, "sent": recipients - 1, "failed": 1},
        "inapp": {"queued": 0, "sent": recipients, "failed": 0},
        "total_recipients": recipients * 2,
    }

    failed = client.get(
        f"/api/v1/announcements/{created['id']}/deliveries",
        params={"channel": "email", "status": "failed"},
        headers=auth(admin),
    ).json()
    assert failed["items"]["total"] == 1
    row = failed["items"]["items"][0]
    assert row["user_email"] == f"two@{FAILURE_DOMAIN}" and FAILURE_DOMAIN in row["error"]
    assert row["attempts"] == MAX_ATTEMPTS
    assert failed["summary"]["email"]["sent"] == recipients - 1, "the summary is unfiltered by design"


# --- 8. preferences and unsubscribe -----------------------------------------------
def test_email_preference_round_trip(client, db, auth, member):
    assert client.get("/api/v1/users/me/email-preferences", headers=auth(member)).json() == {
        "email": "member@ssa.org",
        "email_opt_in": True,
    }
    off = client.post(
        "/api/v1/users/me/email-preferences", json={"email_opt_in": False}, headers=auth(member)
    )
    assert off.status_code == 200 and off.json()["email_opt_in"] is False
    db.expire_all()
    assert db.scalar(select(User.email_opt_in).where(User.email == "member@ssa.org")) is False
    assert client.get("/api/v1/users/me/email-preferences").status_code == 401


def test_unsubscribe_link_works_without_a_session(client, db, make_user):
    user = make_user("member@ssa.org")
    link = create_unsubscribe_token(user)

    response = client.get("/api/v1/unsubscribe", params={"token": link})
    assert response.status_code == 200, response.text
    assert response.json() == {"unsubscribed": True, "email": "m*****@ssa.org"}
    db.expire_all()
    assert db.get(User, user.id).email_opt_in is False

    # Clicking it twice is harmless, not an error.
    assert client.get("/api/v1/unsubscribe", params={"token": link}).status_code == 200


def test_bad_unsubscribe_tokens_are_rejected(client, db, make_user):
    user = make_user("member@ssa.org")
    good = create_unsubscribe_token(user)
    now = datetime.now(UTC)

    expired = jwt.encode(
        {
            "sub": str(user.id),
            "purpose": "unsubscribe",
            "iat": now - timedelta(days=2),
            "exp": now - timedelta(days=1),
        },
        settings.JWT_SECRET,
        algorithm=ALGORITHM,
    )
    wrong_purpose = jwt.encode(
        {"sub": str(user.id), "purpose": "reset-password", "exp": now + timedelta(days=1)},
        settings.JWT_SECRET,
        algorithm=ALGORITHM,
    )
    signed_elsewhere = jwt.encode(
        {"sub": str(user.id), "purpose": "unsubscribe", "exp": now + timedelta(days=1)},
        "not-our-secret-but-long-enough-for-hs256",
        algorithm=ALGORITHM,
    )
    unknown_user = jwt.encode(
        {"sub": str(uuid4()), "purpose": "unsubscribe", "exp": now + timedelta(days=1)},
        settings.JWT_SECRET,
        algorithm=ALGORITHM,
    )

    for token in (expired, wrong_purpose, signed_elsewhere, unknown_user, good[:-3] + "abc", "not-a-jwt"):
        response = client.get("/api/v1/unsubscribe", params={"token": token})
        assert response.status_code == 400, response.text
        assert _code(response) == "INVALID_TOKEN"

    db.expire_all()
    assert db.get(User, user.id).email_opt_in is True, "none of those attempts changed anything"
    assert client.get("/api/v1/unsubscribe").status_code == 422  # token is required


def test_opting_out_drops_mail_that_was_already_queued(client, db, auth, login, monkeypatch, member, organizer_user, make_membership):
    """A queued email is not a promise: if the member opts out first, it does not go out."""
    user = db.scalar(select(User).where(User.email == "member@ssa.org"))
    make_membership(user)
    announcement, _ = post_direct(db, organizer_user, **MEMBERS_ONLY, send_email=True)

    provider = CountingProvider()
    monkeypatch.setattr(worker, "get_provider", lambda: provider)
    client.post(
        "/api/v1/users/me/email-preferences",
        json={"email_opt_in": False},
        headers=auth(login("member@ssa.org")),
    )

    result = process_queued_deliveries(db)
    assert result["failed"] == 1 and result["sent"] == 1  # the in-app row still goes out
    assert provider.sent == [], "opting out must beat mail already sitting in the queue"
    row = next(r for r in deliveries(db, announcement.id) if r.channel == "email")
    assert row.status == "failed" and "unsubscribed" in row.error


# --- 9. row level security --------------------------------------------------------
def test_every_public_table_has_rls_enabled_with_no_policies(pg_engine):
    """The RLS migration must cover every table, this phase's included."""
    with pg_engine.connect() as conn:
        tables = conn.execute(
            text(
                "select tablename, rowsecurity from pg_tables "
                "where schemaname = 'public' and tablename <> 'alembic_version' order by tablename"
            )
        ).all()
        policies = conn.execute(
            text("select count(*) from pg_policies where schemaname = 'public'")
        ).scalar()

    names = {name for name, _ in tables}
    assert {"announcements", "announcement_revisions", "announcement_deliveries"} <= names
    assert [name for name, rls in tables if not rls] == [], "a table without RLS is world-readable"
    assert policies == 0, "RLS with no policies is the point: only the table owner reads"
