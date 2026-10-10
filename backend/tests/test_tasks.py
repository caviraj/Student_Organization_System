"""The task board: who may change what, the activity trail, and where a card lands
(DESIGN.md §4 rule 13, §5 Tasks)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Task, TaskActivity
from app.services import tasks as task_service


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
def fundraiser(make_fundraiser, organizer):
    return make_fundraiser(organizer, days=10)


@pytest.fixture
def tokens(organizer, volunteer, member, login):
    return {
        "organizer": login(organizer.email),
        "volunteer": login(volunteer.email),
        "member": login(member.email),
    }


def trail(client, token, task_id) -> list[dict]:
    """The activity page, newest first, through the API the frontend uses."""
    response = client.get(f"/api/v1/tasks/{task_id}/activity", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    return response.json()["items"]


# --- 1. creating a card -----------------------------------------------------------
def test_create_writes_the_card_at_the_bottom_of_its_column(client, tokens, auth, fundraiser, organizer, volunteer):
    first = client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/tasks",
        json={
            "title": "Bake 200 cookies",
            "category": "baking",
            "assignee_id": str(volunteer.id),
            "due_date": (date.today() + timedelta(days=3)).isoformat(),
        },
        headers=auth(tokens["organizer"]),
    )
    assert first.status_code == 201, first.text
    assert first.json()["position"] == 0
    assert first.json()["status"] == "todo"
    assert first.json()["assignee"]["id"] == str(volunteer.id)

    second = client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/tasks",
        json={"title": "Bake 40 brownies"},
        headers=auth(tokens["organizer"]),
    )
    assert second.status_code == 201, second.text
    assert second.json()["position"] == 1, "a new card lands under the ones already in the column"

    # A card created straight into `doing` gets the bottom of that column, not of `todo`.
    third = client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/tasks",
        json={"title": "Post the posters", "status": "doing"},
        headers=auth(tokens["organizer"]),
    )
    assert (third.json()["status"], third.json()["position"]) == ("doing", 0)


def test_the_created_row_carries_the_title(client, tokens, auth, fundraiser, organizer):
    created = client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/tasks", json={"title": "Print posters"}, headers=auth(tokens["organizer"])
    ).json()
    rows = trail(client, tokens["organizer"], created["id"])
    assert len(rows) == 1
    assert rows[0]["action"] == "created"
    assert rows[0]["to_value"] == "Print posters"
    assert rows[0]["actor"]["id"] == str(organizer.id)


def test_a_title_shorter_than_three_characters_is_refused(client, tokens, auth, fundraiser):
    response = client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/tasks", json={"title": "ab"}, headers=auth(tokens["organizer"])
    )
    assert response.status_code == 422


def test_assignee_must_be_an_active_volunteer_or_above(client, tokens, auth, fundraiser, member):
    response = client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/tasks",
        json={"title": "Run the stall", "assignee_id": str(member.id)},
        headers=auth(tokens["organizer"]),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ASSIGNEE"


def test_due_date_cannot_be_after_the_event(client, tokens, auth, fundraiser):
    response = client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/tasks",
        json={"title": "Clean up", "due_date": (fundraiser.event_date + timedelta(days=1)).isoformat()},
        headers=auth(tokens["organizer"]),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DUE_AFTER_EVENT"
    # The event day itself is fine.
    ok = client.post(
        f"/api/v1/fundraisers/{fundraiser.id}/tasks",
        json={"title": "Clean up", "due_date": fundraiser.event_date.isoformat()},
        headers=auth(tokens["organizer"]),
    )
    assert ok.status_code == 201


def test_a_task_needs_a_board_at_the_database_level(db, organizer):
    """The service answers 422; the CHECK constraint is what makes a homeless card impossible."""
    db.add(Task(title="Homeless card", created_by=organizer.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_tasks_on_a_finished_fundraiser_are_read_only(client, tokens, auth, make_fundraiser, make_task, organizer):
    closed = make_fundraiser(organizer, title="Diwali Stall", status="done")
    task = make_task(closed)

    assert (
        client.post(
            f"/api/v1/fundraisers/{closed.id}/tasks", json={"title": "One more"}, headers=auth(tokens["organizer"])
        ).json()["error"]["code"]
        == "FUNDRAISER_CLOSED"
    )
    assert (
        client.patch(f"/api/v1/tasks/{task.id}", json={"title": "Renamed"}, headers=auth(tokens["organizer"])).json()[
            "error"
        ]["code"]
        == "FUNDRAISER_CLOSED"
    )
    assert (
        client.post(
            f"/api/v1/tasks/{task.id}/move", json={"status": "doing"}, headers=auth(tokens["organizer"])
        ).json()["error"]["code"]
        == "FUNDRAISER_CLOSED"
    )


# --- 2. permissions on one card ---------------------------------------------------
def test_a_member_cannot_touch_a_task(client, tokens, auth, fundraiser, make_task):
    task = make_task(fundraiser, assignee=None)
    assert client.get(f"/api/v1/tasks/{task.id}", headers=auth(tokens["member"])).status_code == 403
    assert client.get(f"/api/v1/tasks/{task.id}").status_code == 401
    assert (
        client.patch(f"/api/v1/tasks/{task.id}", json={"status": "doing"}, headers=auth(tokens["member"])).status_code
        == 403
    )


def test_an_assignee_may_only_move_their_own_card(client, tokens, auth, fundraiser, make_task, organizer, volunteer):
    mine = make_task(fundraiser, assignee=volunteer, title="Bake 200 cookies")
    theirs = make_task(fundraiser, assignee=organizer, title="Print posters")

    moved = client.patch(f"/api/v1/tasks/{mine.id}", json={"status": "doing"}, headers=auth(tokens["volunteer"]))
    assert moved.status_code == 200 and moved.json()["status"] == "doing"

    renamed = client.patch(
        f"/api/v1/tasks/{mine.id}", json={"title": "Bake 400 cookies"}, headers=auth(tokens["volunteer"])
    )
    assert renamed.status_code == 403, "the assignee owns the column, not the card"

    someone_elses = client.patch(
        f"/api/v1/tasks/{theirs.id}", json={"status": "doing"}, headers=auth(tokens["volunteer"])
    )
    assert someone_elses.status_code == 403


def test_an_organizer_may_edit_everything(client, tokens, auth, fundraiser, make_task, organizer, volunteer):
    task = make_task(fundraiser, assignee=volunteer)
    response = client.patch(
        f"/api/v1/tasks/{task.id}",
        json={"title": "Bake 400 cookies", "category": "supplies", "assignee_id": None, "due_date": None},
        headers=auth(tokens["organizer"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["title"], body["category"], body["assignee"], body["due_date"]) == (
        "Bake 400 cookies",
        "supplies",
        None,
        None,
    )


# --- 3. the activity trail --------------------------------------------------------
def test_status_assignee_and_due_changes_each_leave_a_row(
    client, tokens, auth, fundraiser, make_task, organizer, volunteer
):
    task = make_task(fundraiser)

    client.patch(f"/api/v1/tasks/{task.id}", json={"assignee_id": str(volunteer.id)}, headers=auth(tokens["organizer"]))
    due = (date.today() + timedelta(days=2)).isoformat()
    client.patch(f"/api/v1/tasks/{task.id}", json={"due_date": due}, headers=auth(tokens["organizer"]))
    client.patch(f"/api/v1/tasks/{task.id}", json={"status": "doing"}, headers=auth(tokens["organizer"]))
    done = client.patch(f"/api/v1/tasks/{task.id}", json={"status": "done"}, headers=auth(tokens["organizer"]))
    assert done.json()["completed_at"] is not None

    rows = trail(client, tokens["organizer"], task.id)
    assert rows[0]["action"] == "status_changed", "newest first"
    assert {row["action"] for row in rows} == {"assigned", "due_changed", "status_changed"}
    assert sorted((r["from_value"], r["to_value"]) for r in rows if r["action"] == "status_changed") == [
        ("doing", "done"),
        ("todo", "doing"),
    ]

    assigned = next(row for row in rows if row["action"] == "assigned")
    assert (assigned["from_value"], assigned["to_value"]) == ("unassigned", str(volunteer.id))
    due_row = next(row for row in rows if row["action"] == "due_changed")
    assert (due_row["from_value"], due_row["to_value"]) == ("none", due)
    assert due_row["actor"]["id"] == str(organizer.id)

    # Reopening clears the stamp, and editing any other field is recorded as one `edited` row.
    reopened = client.patch(f"/api/v1/tasks/{task.id}", json={"status": "todo"}, headers=auth(tokens["organizer"]))
    assert reopened.json()["completed_at"] is None
    client.patch(f"/api/v1/tasks/{task.id}", json={"title": "Bake more cookies"}, headers=auth(tokens["organizer"]))
    rows = trail(client, tokens["organizer"], task.id)
    assert rows[0]["action"] == "edited" and rows[0]["from_value"] == "title"


def test_status_is_not_logged_when_it_does_not_change(client, tokens, auth, fundraiser, make_task, organizer):
    task = make_task(fundraiser)
    client.patch(f"/api/v1/tasks/{task.id}", json={"status": "todo"}, headers=auth(tokens["organizer"]))
    assert trail(client, tokens["organizer"], task.id) == [], "no change, nothing to record"


# --- 4. moving a card -------------------------------------------------------------
def test_move_re_indexes_both_columns_densely(client, tokens, auth, fundraiser, make_task, organizer, volunteer):
    todo = [make_task(fundraiser, title=f"Todo {i}", position=i) for i in range(3)]
    for i in range(2):
        make_task(fundraiser, title=f"Doing {i}", status="doing", position=i)

    # Todo 0 -> doing, at the top: doing becomes [0, 1, 2] in the new order, todo closes up to 0, 1.
    moved = client.post(
        f"/api/v1/tasks/{todo[0].id}/move", json={"status": "doing", "position": 0}, headers=auth(tokens["organizer"])
    )
    assert moved.status_code == 200, moved.text
    board = client.get(f"/api/v1/fundraisers/{fundraiser.id}/tasks", headers=auth(tokens["volunteer"])).json()
    assert [card["title"] for card in board["columns"]["doing"]] == ["Todo 0", "Doing 0", "Doing 1"]
    assert [card["position"] for card in board["columns"]["doing"]] == [0, 1, 2]
    assert [card["title"] for card in board["columns"]["todo"]] == ["Todo 1", "Todo 2"]
    assert [card["position"] for card in board["columns"]["todo"]] == [0, 1]
    assert board["counts"] == {"todo": 2, "doing": 3, "done": 0}
    assert len(board["items"]) == 5, "the flat list is the same five cards, in board order"


def test_move_clamps_an_impossible_position(client, tokens, auth, fundraiser, make_task, organizer):
    make_task(fundraiser, title="Only card")
    task = make_task(fundraiser, title="Second card")
    moved = client.post(
        f"/api/v1/tasks/{task.id}/move", json={"status": "todo", "position": 99}, headers=auth(tokens["organizer"])
    )
    assert moved.status_code == 200
    board = client.get(f"/api/v1/fundraisers/{fundraiser.id}/tasks", headers=auth(tokens["organizer"])).json()
    assert [card["title"] for card in board["columns"]["todo"]] == ["Only card", "Second card"]
    assert [card["position"] for card in board["columns"]["todo"]] == [0, 1]


def test_move_without_a_position_lands_at_the_bottom(client, tokens, auth, fundraiser, make_task, organizer):
    first = make_task(fundraiser, title="First")
    second = make_task(fundraiser, title="Second", position=1)
    client.post(f"/api/v1/tasks/{first.id}/move", json={"status": "doing"}, headers=auth(tokens["organizer"]))
    client.post(f"/api/v1/tasks/{first.id}/move", json={"status": "todo"}, headers=auth(tokens["organizer"]))
    board = client.get(f"/api/v1/fundraisers/{fundraiser.id}/tasks", headers=auth(tokens["organizer"])).json()
    assert [card["title"] for card in board["columns"]["todo"]] == ["Second", "First"]
    assert second.position == 0


def test_the_assignee_may_move_their_own_card(client, tokens, auth, fundraiser, make_task, organizer, volunteer):
    mine = make_task(fundraiser, assignee=volunteer)
    their_card = make_task(fundraiser, assignee=organizer, title="Print posters")

    ok = client.post(f"/api/v1/tasks/{mine.id}/move", json={"status": "doing"}, headers=auth(tokens["volunteer"]))
    assert ok.status_code == 200, ok.text
    refused = client.post(
        f"/api/v1/tasks/{their_card.id}/move", json={"status": "doing"}, headers=auth(tokens["volunteer"])
    )
    assert refused.status_code == 403


# --- 5. filters, my tasks, delete -------------------------------------------------
def test_list_filters_and_due_date_sort(client, tokens, auth, fundraiser, make_task, organizer, volunteer):
    make_task(fundraiser, title="Overdue job", due_in_days=-1, assignee=volunteer)
    make_task(fundraiser, title="Later job", due_in_days=4, status="doing", category="baking")
    make_task(fundraiser, title="Finished job", status="done", due_in_days=-3)

    overdue = client.get("/api/v1/tasks?overdue=true", headers=auth(tokens["volunteer"])).json()
    assert [card["title"] for card in overdue["items"]] == ["Overdue job"]
    assert overdue["items"][0]["is_overdue"] is True

    baking = client.get("/api/v1/tasks?category=baking", headers=auth(tokens["volunteer"])).json()
    assert [card["title"] for card in baking["items"]] == ["Later job"]

    mine = client.get(f"/api/v1/tasks?assignee_id={volunteer.id}", headers=auth(tokens["volunteer"])).json()
    assert [card["title"] for card in mine["items"]] == ["Overdue job"]

    by_date = client.get("/api/v1/tasks?sort=due_date", headers=auth(tokens["volunteer"])).json()
    assert [card["title"] for card in by_date["items"]][:2] == ["Finished job", "Overdue job"]

    assert client.get("/api/v1/tasks?q=Later", headers=auth(tokens["volunteer"])).json()["total"] == 1


def test_my_tasks_are_only_mine_and_overdue_comes_first(
    client, tokens, auth, fundraiser, make_task, organizer, volunteer
):
    make_task(fundraiser, title="Next week", assignee=volunteer, due_in_days=7)
    make_task(fundraiser, title="Yesterday", assignee=volunteer, due_in_days=-1)
    make_task(fundraiser, title="No date", assignee=volunteer)
    make_task(fundraiser, title="Not mine", assignee=organizer, due_in_days=-5)

    response = client.get("/api/v1/tasks/me", headers=auth(tokens["volunteer"]))
    assert response.status_code == 200, response.text
    assert [card["title"] for card in response.json()["items"]] == ["Yesterday", "Next week", "No date"]
    assert response.json()["total"] == 3


def test_delete_needs_an_organizer_and_keeps_the_trail(
    client, tokens, auth, db, fundraiser, make_task, organizer, volunteer
):
    task = make_task(fundraiser, title="Cancel the cake order")
    task_id = task.id

    refused = client.delete(f"/api/v1/tasks/{task_id}", headers=auth(tokens["volunteer"]))
    assert refused.status_code == 403

    deleted = client.delete(f"/api/v1/tasks/{task_id}", headers=auth(tokens["organizer"]))
    assert deleted.status_code == 204
    db.expire_all()
    assert db.get(Task, task_id) is None

    # task_activity.task_id is ON DELETE SET NULL: the rows stay, and the last one remembers what went.
    rows = list(db.scalars(select(TaskActivity).where(TaskActivity.actor_id == organizer.id)))
    assert [row.action for row in rows] == ["edited"]
    assert rows[0].task_id is None
    assert (rows[0].from_value, rows[0].to_value) == ("Cancel the cake order", "deleted")


# --- 6. the service-level gate ----------------------------------------------------
def test_organizer_check_is_the_shared_rule(make_user, organizer, volunteer):
    assert task_service.is_organizer(organizer) is True
    assert task_service.is_organizer(volunteer) is False
    assert task_service.is_organizer(make_user("treasurer@ssa.org", role="treasurer")) is True


def test_a_status_change_stamps_completed_at(db, fundraiser, make_task, organizer):
    task = make_task(fundraiser)
    assert task.completed_at is None
    task_service.update_task(db, task, {"status": "done"}, organizer)
    assert task.completed_at is not None and task.completed_at <= datetime.now(UTC) + timedelta(seconds=5)
