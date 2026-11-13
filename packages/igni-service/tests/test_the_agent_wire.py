"""`AgentWire` and the models it speaks: attachments, the item body, igni's status, its refusals."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from igni_service import Attachment, EventRefused, IgniService, IgniUnavailable, Producer
from igni_service.agent_wire import (
    AttachmentStored,
    ChatAction,
    ItemStatus,
    ServiceItemRequest,
)
from igni_service.testing import FakeIgni
from igni_service.testing_router import FakeRouter
from igni_service.urls import IgniPaths

from .conftest import ORG

MAX_BYTES = 5 * 1024 * 1024
MAX = Producer.person("u-max")
STORED = {
    "attachment_id": "att-9",
    "filename": "a.png",
    "content_type": "image/png",
    "size": 3,
    "sha256": "ab" * 32,
    "expires_at": "2026-11-20T10:00:00Z",
}
STATUS = {
    "event_id": "ev-1",
    "producer": {"kind": "person", "id": "u-max"},
    "type": "message",
    "state": "pending",
    "created_at": "2026-11-14T10:00:00Z",
    "updated_at": "2026-11-14T10:00:00Z",
}


def answer(monkeypatch: pytest.MonkeyPatch, path: str, reply: Callable[[], httpx.Response]) -> None:
    """Have igni answer what is asked at `path` with `reply()`, and everything else as the fake."""
    real = FakeRouter.handle

    def handle(router: FakeRouter, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith(path):
            router.traffic.record(request)
            return reply()
        return real(router, request)

    monkeypatch.setattr(FakeRouter, "handle", handle)


class TestAnAttachment:
    def test_its_media_type_is_the_one_given_else_guessed_else_opaque(self) -> None:
        assert Attachment.from_bytes("a.png", b"x").content_type == "image/png"
        assert Attachment.from_bytes("a.png", b"x", "text/plain").content_type == "text/plain"
        assert Attachment.from_bytes("a.zzz", b"x").content_type == "application/octet-stream"
        assert Attachment.from_bytes("noext", b"x").content_type == "application/octet-stream"

    def test_five_mib_is_taken_and_one_byte_more_is_not(self) -> None:
        assert len(Attachment.from_bytes("a.bin", b"x" * MAX_BYTES).data) == MAX_BYTES
        with pytest.raises(ValidationError):
            Attachment.from_bytes("a.bin", b"x" * (MAX_BYTES + 1))

    def test_a_name_is_one_to_two_hundred_characters(self) -> None:
        assert Attachment.from_bytes("é" * 200, b"x").filename == "é" * 200
        with pytest.raises(ValidationError):
            Attachment.from_bytes("é" * 201, b"x")
        with pytest.raises(ValidationError):
            Attachment.from_bytes("", b"x")

    def test_a_file_is_read_now_and_named_by_its_file_name(self, tmp_path: Path) -> None:
        source = tmp_path / "sub" / "photo.jpg"
        source.parent.mkdir()
        source.write_bytes(b"first")
        attachment = Attachment.from_path(source)
        source.write_bytes(b"changed")

        assert (attachment.filename, attachment.content_type, attachment.data) == (
            "photo.jpg",
            "image/jpeg",
            b"first",
        )
        assert Attachment.from_path(str(source), "text/plain").content_type == "text/plain"

    def test_a_file_that_is_not_there_or_is_a_directory_raises_the_os_error(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            Attachment.from_path(tmp_path / "missing.pdf")
        with pytest.raises(OSError):  # noqa: PT011 — a directory is IsADirectoryError or PermissionError
            Attachment.from_path(tmp_path)

    def test_it_cannot_be_changed_once_made(self) -> None:
        attachment = Attachment.from_bytes("a.png", b"x")

        with pytest.raises(ValidationError):
            attachment.filename = "b.png"


class TestWhatIgniSaysBack:
    def test_a_stored_file_is_read_as_igni_wrote_it(self) -> None:
        stored = AttachmentStored.model_validate(STORED)

        assert (stored.attachment_id, stored.size, stored.content_type) == ("att-9", 3, "image/png")
        assert stored.expires_at == datetime(2026, 11, 20, 10, tzinfo=UTC)

    def test_a_status_ignores_what_it_does_not_know_and_defaults_the_rest(self) -> None:
        status = ItemStatus.model_validate({**STATUS, "something_new": [1]})

        assert (status.kind, status.thread, status.delivered_at) == ("event", None, None)
        assert not hasattr(status, "something_new")

    def test_a_state_igni_does_not_have_is_not_a_status(self) -> None:
        with pytest.raises(ValidationError):
            ItemStatus.model_validate({**STATUS, "state": "lost"})


class TestTheBodyOfAnItem:
    def test_a_chat_action_takes_three_ops_and_nothing_else(self) -> None:
        assert [ChatAction(op=op).op for op in ("show", "rename", "cancel")] == [
            "show",
            "rename",
            "cancel",
        ]
        with pytest.raises(ValidationError):
            ChatAction(op="delete")  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            ChatAction(op="cancel", extra="x")  # type: ignore[call-arg]

    def test_a_chat_action_title_is_one_to_two_hundred_characters(self) -> None:
        assert ChatAction(op="rename", title="t" * 200).title == "t" * 200
        for title in ("", "t" * 201):
            with pytest.raises(ValidationError):
                ChatAction(op="rename", title=title)

    @pytest.mark.parametrize(
        "field, limit",
        [("text", 65536), ("thread", 200), ("title", 200), ("event_key", 200)],
    )
    def test_each_text_field_stops_where_igni_stops(self, field: str, limit: int) -> None:
        ok = ServiceItemRequest.model_validate(
            {"producer": MAX, "kind": "message", field: "x" * limit}
        )
        assert len(getattr(ok, field)) == limit
        for value in ("", "x" * (limit + 1)):
            with pytest.raises(ValidationError):
                ServiceItemRequest.model_validate(
                    {"producer": MAX, "kind": "message", field: value}
                )

    def test_ten_attachments_are_the_most(self) -> None:
        ServiceItemRequest(producer=MAX, kind="message", attachments=["a"] * 10)
        with pytest.raises(ValidationError):
            ServiceItemRequest(producer=MAX, kind="message", attachments=["a"] * 11)

    def test_a_field_igni_does_not_read_is_refused_and_a_kind_must_be_one_it_has(self) -> None:
        with pytest.raises(ValidationError):
            ServiceItemRequest(producer=MAX, kind="message", priority=1)  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            ServiceItemRequest(producer=MAX, kind="reply")  # type: ignore[arg-type]

    def test_the_key_limit_is_the_events_own(self) -> None:
        from igni_service.events import MAX_KEY

        assert MAX_KEY == 200


class TestUploadingAFile:
    async def test_the_bytes_go_with_their_name_and_type_under_the_orgs_token(
        self, igni: IgniService, fake: FakeIgni
    ) -> None:
        stored = await igni.agents.upload(ORG, Attachment.from_bytes("é à.png", b"\x89PNG"))

        [seen] = fake.traffic.requests_to(IgniPaths.SERVICE_ATTACHMENTS)
        assert (seen.method, seen.query["filename"], seen.body) == ("POST", ["é à.png"], b"\x89PNG")
        assert seen.headers["content-type"] == "image/png"
        assert seen.headers["authorization"].startswith("Bearer service-")
        assert (stored.filename, stored.size) == ("é à.png", 4)

    async def test_files_are_uploaded_in_order_and_their_ids_come_back_in_order(
        self, igni: IgniService, fake: FakeIgni
    ) -> None:
        files = [Attachment.from_bytes(f"{n}.txt", n.encode()) for n in ("b", "a", "c")]

        ids = await igni.agents.uploaded(ORG, files)

        seen = fake.traffic.requests_to(IgniPaths.SERVICE_ATTACHMENTS)
        assert [s.query["filename"][0] for s in seen] == ["b.txt", "a.txt", "c.txt"]
        assert ids == ["att-1", "att-2", "att-3"]
        assert await igni.agents.uploaded(ORG, []) == []

    @pytest.mark.parametrize("status", [200, 201])
    async def test_both_success_statuses_are_read(
        self, igni: IgniService, fake: FakeIgni, monkeypatch: pytest.MonkeyPatch, status: int
    ) -> None:
        answer(
            monkeypatch,
            IgniPaths.SERVICE_ATTACHMENTS,
            lambda: httpx.Response(status, json=STORED),
        )

        stored = await igni.agents.upload(ORG, Attachment.from_bytes("a.png", b"x"))

        assert stored.attachment_id == "att-9"

    @pytest.mark.parametrize("status", [400, 403, 404, 413, 422])
    async def test_a_refusal_says_the_status_and_igni_s_words(
        self, igni: IgniService, fake: FakeIgni, status: int
    ) -> None:
        fake.traffic.fail(IgniPaths.SERVICE_ATTACHMENTS, status)

        with pytest.raises(EventRefused) as refused:
            await igni.agents.upload(ORG, Attachment.from_bytes("a.png", b"x"))

        assert refused.value.status == status
        assert "failing on purpose" in refused.value.detail

    @pytest.mark.parametrize("status", [429, 500, 502, 503])
    async def test_busy_or_broken_igni_is_unavailable_not_a_refusal(
        self, igni: IgniService, fake: FakeIgni, status: int
    ) -> None:
        fake.traffic.fail(IgniPaths.SERVICE_ATTACHMENTS, status)

        with pytest.raises(IgniUnavailable, match=str(status)):
            await igni.agents.upload(ORG, Attachment.from_bytes("a.png", b"x"))

    @pytest.mark.parametrize(
        "reply",
        [
            lambda: httpx.Response(200, text="not json"),
            lambda: httpx.Response(200, json=["a list"]),
            lambda: httpx.Response(201, json={"attachment_id": "att-1"}),
        ],
        ids=["not-json", "wrong-shape", "missing-fields"],
    )
    async def test_an_answer_that_is_not_what_igni_sends_is_unavailable(
        self,
        igni: IgniService,
        fake: FakeIgni,
        monkeypatch: pytest.MonkeyPatch,
        reply: Callable[[], httpx.Response],
    ) -> None:
        answer(monkeypatch, IgniPaths.SERVICE_ATTACHMENTS, reply)

        with pytest.raises(IgniUnavailable, match="something else"):
            await igni.agents.upload(ORG, Attachment.from_bytes("a.png", b"x"))


class TestReadingAStatus:
    async def test_a_status_is_read_from_the_items_own_path(
        self, igni: IgniService, fake: FakeIgni
    ) -> None:
        accepted = await igni.host(ORG).agent(MAX).send_message("hi", thread="t-1")
        fake.agents.settle(accepted.event_id, "delivered")

        status = await igni.agents.status(ORG, accepted.event_id)

        [seen] = fake.traffic.requests_to(IgniPaths.service_event(accepted.event_id))
        assert seen.method == "GET" and seen.headers["authorization"].startswith("Bearer service-")
        assert (status.event_id, status.state, status.thread) == (
            accepted.event_id,
            "delivered",
            "t-1",
        )

    @pytest.mark.parametrize("status", [400, 403, 404])
    async def test_a_4xx_is_a_refusal(self, igni: IgniService, fake: FakeIgni, status: int) -> None:
        fake.traffic.fail(IgniPaths.SERVICE_EVENTS, status)

        with pytest.raises(EventRefused) as refused:
            await igni.agents.status(ORG, "ev-1")

        assert refused.value.status == status

    @pytest.mark.parametrize("status", [500, 502, 503])
    async def test_a_5xx_is_unavailable(
        self, igni: IgniService, fake: FakeIgni, status: int
    ) -> None:
        fake.traffic.fail(IgniPaths.SERVICE_EVENTS, status)

        with pytest.raises(IgniUnavailable, match=str(status)):
            await igni.agents.status(ORG, "ev-1")

    @pytest.mark.parametrize(
        "reply",
        [
            lambda: httpx.Response(200, text="<html>"),
            lambda: httpx.Response(200, json={"event_id": "ev-1"}),
            lambda: httpx.Response(200, json={**STATUS, "state": "lost"}),
        ],
        ids=["not-json", "missing-fields", "unknown-state"],
    )
    async def test_an_answer_that_is_not_a_status_is_unavailable(
        self,
        igni: IgniService,
        fake: FakeIgni,
        monkeypatch: pytest.MonkeyPatch,
        reply: Callable[[], httpx.Response],
    ) -> None:
        answer(monkeypatch, IgniPaths.SERVICE_EVENTS, reply)

        with pytest.raises(IgniUnavailable, match="something else"):
            await igni.agents.status(ORG, "ev-1")

    async def test_unknown_fields_in_igni_s_answer_are_ignored(
        self, igni: IgniService, fake: FakeIgni, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        answer(
            monkeypatch,
            IgniPaths.SERVICE_EVENTS,
            lambda: httpx.Response(200, json={**STATUS, "newer": True}),
        )

        assert (await igni.agents.status(ORG, "ev-1")).event_id == "ev-1"


class TestPostingAnItem:
    async def test_an_item_is_retried_when_igni_could_not_take_it_and_not_when_it_refused(
        self, igni: IgniService, fake: FakeIgni
    ) -> None:
        igni.events._sleep = _no_sleep
        item = ServiceItemRequest(producer=MAX, kind="message", text="hi")

        fake.traffic.fail(IgniPaths.SERVICE_ITEMS, 503)
        with pytest.raises(IgniUnavailable):
            await igni.agents.item(ORG, item)
        assert len(fake.traffic.requests_to(IgniPaths.SERVICE_ITEMS)) == 3

        fake.traffic.reset()
        fake.traffic.fail(IgniPaths.SERVICE_ITEMS, 403)
        with pytest.raises(EventRefused):
            await igni.agents.item(ORG, item)
        assert len(fake.traffic.requests_to(IgniPaths.SERVICE_ITEMS)) == 1

    async def test_an_item_goes_to_the_items_path_and_an_event_to_the_events_path(
        self, igni: IgniService, fake: FakeIgni
    ) -> None:
        from igni_service.events import ServiceEventRequest

        await igni.agents.item(ORG, ServiceItemRequest(producer=MAX, kind="chat", title="T"))
        await igni.agents.event(ORG, ServiceEventRequest(producer=MAX, type="claim.created"))

        assert [i.kind for i in fake.agents.items] == ["chat", "event"]
        assert len(fake.traffic.requests_to(IgniPaths.SERVICE_ITEMS)) == 1
        assert len(fake.traffic.requests_to(IgniPaths.SERVICE_EVENTS)) == 1


async def _no_sleep(_: float) -> None:
    return None
