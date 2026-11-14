"""The fake's agent channel: what it stores, refuses, answers and forgets.

Driven at `FakeAgents` with the bodies a service posts, so igni's rules
(grants, membership, once-only keys, files named by one item) are seen
as igni's answers and not through the SDK that sends them.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import httpx

from igni_service.testing_items import ALL_GRANTS, FakeAgents

ORG = "org-acme"
NOW = 1_700_000_000.0
ADA = {"kind": "person", "id": "u-ada"}


def agents(*members: str) -> FakeAgents:
    belongs = set(members or ("u-ada",))
    return FakeAgents(is_member=lambda org, user: org == ORG and user in belongs, clock=lambda: NOW)


def event(
    fake: FakeAgents, *, client: str = "c-1", org: str = ORG, **body: object
) -> httpx.Response:
    fields = {"producer": ADA, "type": "claim.created", **body}
    return fake.event(json.dumps(fields).encode(), client, org)


def item(
    fake: FakeAgents, *, client: str = "c-1", org: str = ORG, **body: object
) -> httpx.Response:
    fields = {"producer": ADA, "kind": "message", "text": "hi", **body}
    return fake.item(json.dumps(fields).encode(), client, org)


def upload(
    fake: FakeAgents,
    data: bytes = b"data",
    *,
    client: str = "c-1",
    filename: str = "a.txt",
    content_type: str = "text/plain",
) -> httpx.Response:
    return fake.upload(client_id=client, filename=filename, content_type=content_type, data=data)


def on_the_wire(moment: datetime) -> str:
    """A UTC time as igni's JSON writes it: ISO 8601 with `Z`."""
    return moment.isoformat().replace("+00:00", "Z")


def detail(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["detail"]


# ── Events and items ────────────────────────────────────────────────


def test_the_grants_are_the_three_an_extension_may_declare() -> None:
    assert {"messages", "attachments", "chats"} == ALL_GRANTS
    assert agents().grants == set(ALL_GRANTS)
    assert agents().max_bytes == 5 * 1024 * 1024


def test_a_plain_event_is_stored_with_its_fields_and_answered_202() -> None:
    fake = agents()

    answer = event(fake, payload={"n": 1}, event_key="k-1")

    assert (answer.status_code, answer.json()) == (
        202,
        {"event_id": "ev-1", "duplicate": False, "expires_at": "2023-11-28T22:13:20Z"},
    )
    (stored,) = fake.items
    assert (stored.event_id, stored.org_id, stored.client_id) == ("ev-1", ORG, "c-1")
    assert (stored.kind, stored.type, stored.payload) == ("event", "claim.created", {"n": 1})
    assert (stored.event_key, stored.state, stored.producer.id) == ("k-1", "pending", "u-ada")
    assert stored.created_at == datetime.fromtimestamp(NOW, UTC)


def test_an_item_is_stored_with_its_kind_thread_text_title_run_flag_and_action() -> None:
    fake = agents()

    message = item(fake, thread="t-1", start_run=False)
    chat = item(fake, kind="chat", text=None, title="Topic")
    action = item(fake, kind="action", text=None, action={"op": "rename", "title": "New"})

    assert [r.json()["event_id"] for r in (message, chat, action)] == ["ev-1", "ev-2", "ev-3"]
    first, second, third = fake.items
    assert (first.kind, first.type, first.thread, first.text, first.start_run) == (
        "message",
        "message",
        "t-1",
        "hi",
        False,
    )
    assert (second.kind, second.title, second.start_run) == ("chat", "Topic", True)
    assert third.action is not None
    assert (third.action.op, third.action.title) == ("rename", "New")


def test_a_body_igni_cannot_read_is_refused_with_422_and_nothing_is_stored() -> None:
    fake = agents()

    for answer in (
        fake.event(b"nonsense", "c-1", ORG),
        fake.event(b'{"producer": {"kind": "person", "id": "u-ada"}}', "c-1", ORG),
        fake.item(b"nonsense", "c-1", ORG),
        fake.item(b'{"producer": {"kind": "person", "id": "u-ada"}, "kind": "poem"}', "c-1", ORG),
    ):
        assert answer.status_code == 422
        assert answer.json()["detail"]
    assert fake.items == []


def test_event_ids_follow_the_count_and_restart_after_a_reset() -> None:
    fake = agents()
    event(fake)
    event(fake)

    fake.reset()
    answer = event(fake)

    assert answer.json()["event_id"] == "ev-1"
    assert len(fake.items) == 1


def test_a_person_who_is_not_a_member_is_not_found_but_a_service_or_app_is_not_checked() -> None:
    fake = agents()

    stranger = event(fake, producer={"kind": "person", "id": "u-stranger"})
    app = event(fake, producer={"kind": "app", "id": "app-unknown"})

    assert detail(stranger) == (404, "no such producer in this organisation")
    assert app.status_code == 202
    assert len(fake.items) == 1


def test_a_person_is_checked_in_the_organisation_of_the_token() -> None:
    fake = agents()

    assert detail(event(fake, org="org-other")) == (404, "no such producer in this organisation")


def test_the_same_key_from_the_same_producer_and_organisation_is_stored_once() -> None:
    fake = agents()
    first = event(fake, event_key="k", payload={"a": 1})

    again = event(fake, event_key="k", payload={"a": 2}, type="other")

    assert again.json() == {
        "event_id": first.json()["event_id"],
        "duplicate": True,
        "expires_at": first.json()["expires_at"],
    }
    assert again.status_code == 202
    assert len(fake.items) == 1


def test_a_key_is_not_a_duplicate_for_another_producer_organisation_or_without_one() -> None:
    fake = agents("u-ada", "u-max")
    event(fake, event_key="k")

    other_producer = event(fake, event_key="k", producer={"kind": "person", "id": "u-max"})
    nobody_key_a, nobody_key_b = event(fake), event(fake)

    assert other_producer.json()["duplicate"] is False
    assert [nobody_key_a.json()["duplicate"], nobody_key_b.json()["duplicate"]] == [False, False]
    assert len(fake.items) == 4


def test_a_duplicate_is_answered_before_its_files_are_looked_at() -> None:
    fake = agents()
    item(fake, event_key="k")

    answer = item(fake, event_key="k", attachments=["att-nope"])

    assert answer.json()["duplicate"] is True


# ── Grants ──────────────────────────────────────────────────────────


def test_a_message_needs_messages_and_a_thread_or_chat_needs_chats() -> None:
    fake = agents()
    fake.grants = {"chats"}
    assert detail(item(fake)) == (
        403,
        "the extension does not declare service.messages in permissions.service",
    )
    fake.grants = {"messages"}
    assert detail(item(fake, thread="t-1")) == (
        403,
        "the extension does not declare service.chats in permissions.service",
    )
    assert detail(item(fake, kind="chat", text=None, title="x"))[0] == 403
    assert detail(item(fake, kind="action", text=None, action={"op": "cancel"}))[0] == 403
    assert item(fake).status_code == 202


def test_a_threaded_message_needs_both_grants_and_several_missing_are_listed_sorted() -> None:
    fake = agents()
    fake.grants = set()

    answer = item(fake, thread="t-1", attachments=["att-1"])

    assert detail(answer) == (
        403,
        "the extension does not declare service.attachments, service.chats, service.messages"
        " in permissions.service",
    )
    assert fake.items == []


def test_a_plain_event_needs_no_grant() -> None:
    fake = agents()
    fake.grants = set()

    assert event(fake).status_code == 202


# ── Files ───────────────────────────────────────────────────────────


def test_an_upload_is_kept_and_answered_with_its_id_size_digest_and_a_day_of_life() -> None:
    fake = agents()

    answer = upload(fake, b"hello", content_type="text/plain; charset=utf-8")

    assert answer.status_code == 201
    assert answer.json() == {
        "attachment_id": "att-1",
        "filename": "a.txt",
        "content_type": "text/plain",
        "size": 5,
        "sha256": hashlib.sha256(b"hello").hexdigest(),
        "expires_at": on_the_wire(datetime.fromtimestamp(NOW, UTC) + timedelta(days=1)),
    }
    kept = fake.uploads["att-1"]
    assert (kept.client_id, kept.data, kept.content_type, kept.event_id) == (
        "c-1",
        b"hello",
        "text/plain",
        None,
    )
    assert upload(fake).json()["attachment_id"] == "att-2"


def test_a_content_type_without_a_media_type_is_octet_stream() -> None:
    fake = agents()

    for given in ("", "  ", "; charset=utf-8"):
        assert upload(fake, content_type=given).json()["content_type"] == "application/octet-stream"
    assert upload(fake, content_type="IMAGE/PNG ;x=y").json()["content_type"] == "IMAGE/PNG"


def test_a_file_name_that_is_empty_or_a_path_is_refused() -> None:
    fake = agents()

    for name in ("", "a/b.txt", "..\\b.txt", "/etc"):
        assert detail(upload(fake, filename=name)) == (
            400,
            "filename must be a file name, not a path",
        )
    assert upload(fake, filename="résumé 😀.txt").status_code == 201
    assert len(fake.uploads) == 1


def test_a_file_with_no_bytes_is_refused() -> None:
    assert detail(upload(agents(), b"")) == (400, "an attachment has no bytes")


def test_a_file_of_exactly_the_limit_is_kept_and_one_byte_more_is_too_large() -> None:
    fake = agents()
    fake.max_bytes = 8

    assert upload(fake, b"x" * 8).status_code == 201
    assert detail(upload(fake, b"x" * 9)) == (413, "too large")
    assert len(fake.uploads) == 1


def test_an_upload_needs_the_attachments_grant() -> None:
    fake = agents()
    fake.grants.discard("attachments")

    assert detail(upload(fake)) == (
        403,
        "the extension does not declare service.attachments in permissions.service",
    )
    assert fake.uploads == {}


def test_an_item_links_the_files_it_names_and_each_file_is_named_by_one_item() -> None:
    fake = agents()
    upload(fake)

    first = item(fake, attachments=["att-1"])
    second = item(fake, attachments=["att-1"])

    assert first.status_code == 202
    assert detail(second) == (400, "an attachment is not this service's")
    assert fake.uploads["att-1"].event_id == "ev-1"
    assert fake.items[0].attachments == ["att-1"]
    assert len(fake.items) == 1


def test_a_file_that_is_unknown_or_another_services_is_refused() -> None:
    fake = agents()
    upload(fake, client="c-2")

    unknown = item(fake, attachments=["att-9"])
    foreign = item(fake, attachments=["att-1"])

    for answer in (unknown, foreign):
        assert detail(answer) == (400, "an attachment is not this service's")
    assert fake.uploads["att-1"].event_id is None
    assert fake.items == []


def test_the_grant_for_files_is_checked_when_an_item_names_one() -> None:
    fake = agents()
    upload(fake)
    fake.grants.discard("attachments")

    assert item(fake, attachments=["att-1"]).status_code == 403
    assert item(fake).status_code == 202


# ── Status and settle ───────────────────────────────────────────────


def test_the_status_of_an_item_is_its_state_and_its_fourteen_days() -> None:
    fake = agents()
    item(fake, thread="t-1", event_key="k")

    answer = fake.status("ev-1", "c-1")

    assert answer.status_code == 200
    created = datetime.fromtimestamp(NOW, UTC)
    assert answer.json() == {
        "event_id": "ev-1",
        "producer": ADA,
        "kind": "message",
        "type": "message",
        "thread": "t-1",
        "event_key": "k",
        "state": "pending",
        "dropped_reason": None,
        "failed_reason": None,
        "not_handled_reason": None,
        "created_at": on_the_wire(created),
        "expires_at": on_the_wire(created + timedelta(days=14)),
        "delivered_at": None,
        "updated_at": on_the_wire(created),
    }


def test_a_failed_item_is_undeliverable_and_a_not_handled_one_names_its_type() -> None:
    fake = agents()
    event(fake)
    event(fake, type="claim.paid")
    fake.settle("ev-1", "failed")
    fake.settle("ev-2", "not_handled")

    failed, unhandled = fake.status("ev-1", "c-1").json(), fake.status("ev-2", "c-1").json()

    assert (failed["state"], failed["failed_reason"], failed["not_handled_reason"]) == (
        "failed",
        "undeliverable",
        None,
    )
    assert (unhandled["state"], unhandled["failed_reason"], unhandled["not_handled_reason"]) == (
        "not_handled",
        None,
        "no handler for claim.paid",
    )


def test_an_item_of_another_service_or_an_unknown_id_is_not_found() -> None:
    fake = agents()
    event(fake)

    for answer in (fake.status("ev-1", "c-2"), fake.status("ev-9", "c-1")):
        assert detail(answer) == (404, "No such event from this service")


def test_settling_moves_the_one_item_and_an_unknown_id_changes_nothing() -> None:
    fake = agents()
    event(fake)
    event(fake)

    fake.settle("ev-2", "delivered")
    fake.settle("ev-9", "dropped")

    assert [i.state for i in fake.items] == ["pending", "delivered"]
    fake.settle("ev-2", "expired")
    assert fake.items[1].state == "expired"


def test_a_reset_forgets_items_and_files_and_grants_everything_again() -> None:
    fake = agents()
    upload(fake)
    event(fake)
    fake.grants = set()

    fake.reset()

    assert (fake.items, fake.uploads) == ([], {})
    assert fake.grants == set(ALL_GRANTS)
    assert upload(fake).json()["attachment_id"] == "att-1"
