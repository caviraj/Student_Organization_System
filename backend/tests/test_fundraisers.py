"""Fundraisers: the lifecycle, the progress arithmetic, the health rule and the cost of the list
(DESIGN.md §4 rule 13, §5 Fundraisers)."""

from datetime import date, timedelta

import pytest
from sqlalchemy import event, text

from app.core.errors import AppError
from app.models import Transaction
from app.services import fundraisers as fundraiser_service
from app.services.fundraisers import health_of

GOAL = 500000


@pytest.fixture
def organizer(make_user):
    return make_user("organizer@ssa.org", role="organizer")


@pytest.fixture
def volunteer(make_user):
    return make_user("volunteer@ssa.org", role="volunteer")


@pytest.fixture
def member(make_user):
    return make_user("member01@ssa.org", role="member")


@pytest.fixture
def tokens(organizer, volunteer, member, login):
    return {
        "organizer": login(organizer.email),
        "volunteer": login(volunteer.email),
        "member": login(member.email),
    }


# --- 1. permissions ---------------------------------------------------------------
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/fundraisers"),
        ("get", "/api/v1/fundraisers/{id}"),
        ("get", "/api/v1/fundraisers/{id}/tasks"),
        ("get", "/api/v1/fundraisers/{id}/income"),
        ("get", "/api/v1/fundraisers/{id}/volunteers"),
    ],
)
@pytest.mark.parametrize("caller", ["guest", "member", "volunteer"])
def test_read_permissions(client, tokens, auth, make_fundraiser, organizer, method, path, caller):
    fundraiser = make_fundraiser(organizer)
    url = path.format(id=fundraiser.id)
    if caller == "guest":
        response = getattr(client, method)(url)
        assert response.status_code == 401
    else:
        response = getattr(client, method)(url, headers=auth(tokens[caller]))
        expected = 403 if caller == "member" else 200
        assert response.status_code == expected, response.text


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/v1/fundraisers", {"title": "New Drive", "goal_amount": 100000, "event_date": None}),
        ("patch", "/api/v1/fundraisers/{id}", {"title": "Renamed drive"}),
        ("post", "/api/v1/fundraisers/{id}/tasks", {"title": "Collect the tins"}),
        ("post", "/api/v1/fundraisers/{id}/income", {"amount": 100000}),
    ],
)
@pytest.mark.parametrize("caller", ["guest", "member", "volunteer", "organizer"])
def test_write_permissions(client, tokens, auth, make_fundraiser, organizer, method, path, body, caller):
    fundraiser = make_fundraiser(organizer)
    url = path.format(id=fundraiser.id)
    payload = {**body}
    if payload.get("event_date", "absent") is None:
        payload["event_date"] = (date.today() + timedelta(days=5)).isoformat()

    if caller == "guest":
        assert getattr(client, method)(url, json=payload).status_code == 401
        return
    response = getattr(client, method)(url, json=payload, headers=auth(tokens[caller]))
    # A volunteer reads the board but cannot plan the fundraiser; organizer and above may write.
    if caller == "organizer":
        assert response.status_code < 400, response.text
    else:
        assert response.status_code == 403, response.text


# --- 2. lifecycle -----------------------------------------------------------------
def test_create_defaults_to_planning_and_runs_the_full_lifecycle(client, tokens, auth, db):
    created = client.post(
        "/api/v1/fundraisers",
        json={
            "title": "Book Drive",
            "goal_amount": GOAL,
            "event_date": (date.today() + timedelta(days=30)).isoformat(),
        },
        headers=auth(tokens["organizer"]),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "planning"
    assert body["progress"]["health"] == "on_track"
    assert body["progress"]["tasks"]["percent_done"] == 0, "an empty board is 0%, not a division error"
    assert body["progress"]["percent_of_goal"] == 0
    fundraiser_id = body["id"]

    active = client.patch(
        f"/api/v1/fundraisers/{fundraiser_id}", json={"status": "active"}, headers=auth(tokens["organizer"])
    )
    assert active.status_code == 200 and active.json()["status"] == "active"

    done = client.patch(
        f"/api/v1/fundraisers/{fundraiser_id}", json={"status": "done"}, headers=auth(tokens["organizer"])
    )
    assert done.status_code == 200
    assert done.json()["status"] == "done"
    assert done.json()["completed_at"] is not None
    assert done.json()["progress"]["health"] == "completed"


def test_planning_cannot_jump_straight_to_done(client, tokens, auth, make_fundraiser, organizer):
    fundraiser = make_fundraiser(organizer)
    response = client.patch(
        f"/api/v1/fundraisers/{fundraiser.id}", json={"status": "done"}, headers=auth(tokens["organizer"])
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"


def test_done_cannot_go_backwards(client, tokens, auth, make_fundraiser, organizer):
    fundraiser = make_fundraiser(organizer, status="done")
    response = client.patch(
        f"/api/v1/fundraisers/{fundraiser.id}", json={"status": "active"}, headers=auth(tokens["organizer"])
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"


def test_closing_with_open_tasks_needs_force(client, tokens, auth, db, make_fundraiser, make_task, organizer):
    fundraiser = make_fundraiser(organizer, status="active")
    make_task(fundraiser)
    make_task(fundraiser, status="done")

    refused = client.patch(
        f"/api/v1/fundraisers/{fundraiser.id}", json={"status": "done"}, headers=auth(tokens["organizer"])
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "OPEN_TASKS"
    assert refused.json()["error"]["details"]["open_count"] == 1

    forced = client.patch(
        f"/api/v1/fundraisers/{fundraiser.id}?force=true", json={"status": "done"}, headers=auth(tokens["organizer"])
    )
    assert forced.status_code == 200 and forced.json()["status"] == "done"


def test_only_the_owner_or_an_admin_may_patch(client, tokens, auth, make_user, login, make_fundraiser, organizer):
    fundraiser = make_fundraiser(organizer)
    admin = make_user("admin@ssa.org", role="admin")
    # A second organizer, not a volunteer: `require_role` already stopped the volunteer at the door,
    # so NOT_OWNER is the rule that has to hold between two people who both may write.
    other = make_user("organizer2@ssa.org", role="organizer")

    refused = client.patch(
        f"/api/v1/fundraisers/{fundraiser.id}", json={"title": "Hijacked"}, headers=auth(login(other.email))
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "NOT_OWNER"

    allowed = client.patch(
        f"/api/v1/fundraisers/{fundraiser.id}", json={"title": "Owned edit"}, headers=auth(tokens["organizer"])
    )
    assert allowed.status_code == 200 and allowed.json()["title"] == "Owned edit"

    # The admin is above the owner rule: someone has to be able to fix a board whose owner left.
    fixed = client.patch(
        f"/api/v1/fundraisers/{fundraiser.id}", json={"title": "Admin edit"}, headers=auth(login(admin.email))
    )
    assert fixed.status_code == 200 and fixed.json()["title"] == "Admin edit"


def test_a_past_event_date_is_refused_unless_the_fundraiser_is_done(client, tokens, auth, make_fundraiser, organizer):
    past = (date.today() - timedelta(days=1)).isoformat()
    refused = client.post(
        "/api/v1/fundraisers",
        json={"title": "Yesterday's idea", "goal_amount": GOAL, "event_date": past},
        headers=auth(tokens["organizer"]),
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "VALIDATION_ERROR"

    # Recording one that already happened is fine, and so is moving a finished one onto its real date.
    recorded = client.post(
        "/api/v1/fundraisers",
        json={"title": "Diwali Stall", "goal_amount": GOAL, "event_date": past, "status": "done"},
        headers=auth(tokens["organizer"]),
    )
    assert recorded.status_code == 201 and recorded.json()["status"] == "done"


def test_owner_must_be_an_organizer(client, tokens, auth, member):
    response = client.post(
        "/api/v1/fundraisers",
        json={
            "title": "Member's idea",
            "goal_amount": GOAL,
            "event_date": (date.today() + timedelta(days=5)).isoformat(),
            "owner_id": str(member.id),
        },
        headers=auth(tokens["organizer"]),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_OWNER"


# --- 3. progress arithmetic -------------------------------------------------------
def test_progress_counts_money_and_dates(db, make_fundraiser, make_task, organizer, volunteer):
    fundraiser = make_fundraiser(organizer, goal=GOAL, days=10)
    make_task(fundraiser, status="done", assignee=volunteer, due_in_days=-2)
    make_task(fundraiser, status="doing", assignee=volunteer, due_in_days=1)
    make_task(fundraiser, status="todo", assignee=volunteer, due_in_days=20)
    make_task(fundraiser, status="todo", due_in_days=-1)  # overdue and nobody's

    db.add_all(
        [
            Transaction(direction="in", amount=200000, source="fundraiser", fundraiser_id=fundraiser.id),
            Transaction(direction="out", amount=50000, source="fundraiser", fundraiser_id=fundraiser.id),
        ]
    )
    db.commit()

    progress = fundraiser_service.compute_progress(db, fundraiser)
    assert progress["tasks"] == {
        "total": 4,
        "todo": 2,
        "doing": 1,
        "done": 1,
        "overdue": 1,
        "due_soon": 1,
        "unassigned": 1,
        "percent_done": 25,
    }
    # `out` rows are not money raised: only the `in` side counts.
    assert progress["raised"] == 200000
    assert progress["goal"] == GOAL
    assert progress["percent_of_goal"] == 40
    assert progress["days_to_event"] == 10
    assert progress["by_category"] == [{"category": "other", "total": 4, "done": 1}]
    assert {row["name"] or "unassigned" for row in progress["by_assignee"]} == {"unassigned", volunteer.full_name}


def test_progress_on_an_empty_board_does_not_divide_by_zero(db, make_fundraiser, organizer):
    fundraiser = make_fundraiser(organizer, goal=1)
    progress = fundraiser_service.compute_progress(db, fundraiser)
    assert progress["tasks"]["percent_done"] == 0
    assert progress["percent_of_goal"] == 0
    assert progress["health"] == "on_track"
    assert progress["by_category"] == [] and progress["by_assignee"] == []


def test_an_empty_fundraiser_that_has_passed_its_date_is_behind(db, make_fundraiser, organizer):
    fundraiser = make_fundraiser(organizer, days=-1)
    assert fundraiser_service.compute_progress(db, fundraiser)["health"] == "behind"


# --- 4. the health rule, one row per branch ---------------------------------------
@pytest.mark.parametrize(
    ("status", "overdue", "unassigned", "days", "percent", "expected"),
    [
        # done wins over everything: a finished fundraiser is never "behind".
        ("done", 9, 9, -30, 0, "completed"),
        # behind: 3+ overdue, or the date is close with most work left, or the date has gone.
        ("active", 3, 0, 30, 100, "behind"),
        ("active", 0, 0, 3, 69, "behind"),
        ("active", 0, 0, -1, 100, "behind"),
        # at_risk: one overdue, or two cards nobody owns, or a week out and under half done.
        ("active", 1, 0, 30, 100, "at_risk"),
        ("active", 0, 2, 30, 100, "at_risk"),
        ("active", 0, 0, 7, 49, "at_risk"),
        # on_track: none of the above. Two overdue is still only at_risk, not behind.
        ("active", 2, 0, 30, 100, "at_risk"),
        ("active", 0, 0, 0, 100, "on_track"),
        ("active", 0, 1, 30, 100, "on_track"),
        ("active", 0, 0, 7, 50, "on_track"),
        ("planning", 0, 1, 30, 0, "on_track"),
    ],
)
def test_health_rule_covers_every_branch(status, overdue, unassigned, days, percent, expected):
    assert health_of(status, overdue, unassigned, days, percent) == expected


# --- 5. the list must not cost a query per row ------------------------------------
def test_list_fundraisers_is_not_n_plus_one(client, tokens, auth, db, make_fundraiser, make_task, organizer, volunteer):
    """Ten fundraisers with five cards each. The bound is the point of `progress_for`: the page
    needs its rows, its count, one grouped task query and one grouped ledger query - anything
    proportional to the page size is the bug this test exists to catch."""
    for index in range(10):
        fundraiser = make_fundraiser(organizer, title=f"Drive {index}")
        for card in range(5):
            make_task(
                fundraiser,
                title=f"Card {card}",
                status=("todo", "doing", "done")[card % 3],
                assignee=volunteer if card % 2 else None,
                due_in_days=card - 2,
            )

    statements = []
    engine = db.get_bind()

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = client.get("/api/v1/fundraisers?page_size=20", headers=auth(tokens["volunteer"]))
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 10
    assert len(statements) <= 8, f"{len(statements)} statements for 10 fundraisers: {statements}"
    # And the numbers are still right, so the bound was not bought by dropping the progress.
    assert response.json()["items"][0]["progress"]["tasks_total"] == 5


# --- 6. volunteers, assignable users ---------------------------------------------
def test_volunteers_lists_everyone_on_the_board(client, tokens, auth, make_fundraiser, make_task, organizer, volunteer):
    fundraiser = make_fundraiser(organizer)
    make_task(fundraiser, assignee=volunteer)
    make_task(fundraiser, assignee=volunteer, status="done")
    make_task(fundraiser, assignee=organizer, status="done")
    make_task(fundraiser)  # unassigned: not a volunteer on this board

    response = client.get(f"/api/v1/fundraisers/{fundraiser.id}/volunteers", headers=auth(tokens["volunteer"]))
    assert response.status_code == 200
    rows = {row["user"]["full_name"]: row for row in response.json()}
    assert len(rows) == 2
    volunteer_row = rows[volunteer.full_name]
    assert (volunteer_row["tasks_total"], volunteer_row["tasks_done"], volunteer_row["open_tasks"]) == (2, 1, 1)


def test_assignable_users_are_volunteer_and_above(client, tokens, auth, organizer, volunteer, member):
    response = client.get("/api/v1/users/assignable", headers=auth(tokens["organizer"]))
    assert response.status_code == 200
    emails = {row["email"] for row in response.json()}
    assert emails == {organizer.email, volunteer.email}

    assert client.get("/api/v1/users/assignable", headers=auth(tokens["volunteer"])).status_code == 403
    assert client.get("/api/v1/users/assignable").status_code == 401


# --- 7. RLS -----------------------------------------------------------------------
def test_every_new_table_has_rls_enabled(db):
    rows = db.execute(
        text(
            "select tablename, rowsecurity from pg_tables "
            "where schemaname = 'public' and tablename in ('fundraisers', 'tasks', 'task_activity')"
        )
    ).all()
    assert len(rows) == 3
    assert all(enabled for _table, enabled in rows), "Supabase would publish these over REST without RLS"
    policies = db.scalar(
        text(
            "select count(*) from pg_policies "
            "where schemaname = 'public' and tablename in ('fundraisers', 'tasks', 'task_activity')"
        )
    )
    assert policies == 0, "RLS with no policies is the point: only the table owner reads"


# --- 8. the lifecycle gate the task service leans on -----------------------------
def test_assert_open_refuses_a_finished_fundraiser(db, make_fundraiser, organizer):
    fundraiser = make_fundraiser(organizer, status="done")
    with pytest.raises(AppError) as excinfo:
        fundraiser_service.assert_open(fundraiser)
    assert excinfo.value.code == "FUNDRAISER_CLOSED"
