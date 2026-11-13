"""`Agent` and `Chat`: what each method sends, in which order, and what it refuses to send."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from igni_service import Agent, Attachment, EventRefused, IgniService, Producer
from igni_service.agent_wire import ChatAction
from igni_service.testing import FakeIgni
from igni_service.urls import IgniPaths

from .conftest import ORG

MAX = Producer.person("u-max")
SOON = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)
PNG = Attachment.from_bytes("a.png", b"\x89PNG")


@pytest.fixture
def agent(igni: IgniService) -> Agent:
    return igni.host(ORG).agent(MAX)


def sent_items(fake: FakeIgni) -> list[dict[str, object]]:
    return [s.json_body() for s in fake.traffic.requests_to(IgniPaths.SERVICE_ITEMS)]


def test_an_agent_says_whose_it_is_and_a_chat_handle_sends_nothing(
    agent: Agent, fake: FakeIgni
) -> None:
    chat = agent.chat("claim:1")

    assert agent.producer == MAX
    assert chat.thread == "claim:1"
    assert fake.traffic.seen == []


class TestAMessage:
    async def test_its_title_and_start_run_and_expiry_go_on_the_wire(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        await agent.send_message(
            "hi", thread="t", title="Claim", start_run=False, expires_at=SOON, event_key="k"
        )

        assert sent_items(fake) == [
            {
                "producer": {"kind": "person", "id": "u-max"},
                "kind": "message",
                "thread": "t",
                "text": "hi",
                "title": "Claim",
                "start_run": False,
                "event_key": "k",
                "expires_at": "2026-11-20T09:30:00Z",
            }
        ]

    async def test_without_a_thread_none_is_sent_and_a_title_in_unicode_survives(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        await agent.send_message("hé 😀")
        await agent.send_message("x", thread="schade:é", title="Überprüfung ✓")

        first, second = sent_items(fake)
        assert "thread" not in first and first["text"] == "hé 😀"
        assert (second["thread"], second["title"]) == ("schade:é", "Überprüfung ✓")

    async def test_the_same_key_after_a_lost_reply_gives_back_the_stored_item(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        first = await agent.send_message("hi", event_key="claim:1")
        again = await agent.send_message("hi", event_key="claim:1")

        assert again.duplicate and again.event_id == first.event_id
        assert len(fake.agents.items) == 1

    @pytest.mark.parametrize("text", ["", "x" * 65537])
    async def test_a_text_igni_would_refuse_is_caught_and_nothing_is_sent(
        self, agent: Agent, fake: FakeIgni, text: str
    ) -> None:
        with pytest.raises(ValidationError):
            await agent.send_message(text)

        assert fake.traffic.seen == []

    async def test_a_text_of_exactly_the_most_is_sent(self, agent: Agent, fake: FakeIgni) -> None:
        await agent.send_message("x" * 65536)

        assert len(str(sent_items(fake)[0]["text"])) == 65536


class TestFiles:
    async def test_a_failed_upload_stops_the_item_and_leaves_earlier_files_unclaimed(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        fake.agents.grants = {"messages", "chats"}  # may send, may not attach

        with pytest.raises(EventRefused) as refused:
            await agent.send_message("see", attachments=[PNG, PNG])

        assert refused.value.status == 403
        assert len(fake.traffic.requests_to(IgniPaths.SERVICE_ATTACHMENTS)) == 1
        assert fake.traffic.requests_to(IgniPaths.SERVICE_ITEMS) == []

    async def test_none_and_an_empty_list_upload_nothing_and_send_no_attachments_key(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        await agent.send_message("a", attachments=None)
        await agent.send_message("b", attachments=[])

        assert fake.traffic.requests_to(IgniPaths.SERVICE_ATTACHMENTS) == []
        assert all("attachments" not in body for body in sent_items(fake))

    async def test_eleven_files_are_caught_before_the_item_is_sent(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        await agent.send_message("ten", attachments=[PNG] * 10)
        fake.traffic.reset()

        with pytest.raises(ValidationError):
            await agent.send_message("eleven", attachments=[PNG] * 11)

        assert fake.traffic.seen == [], "no file is uploaded for an item that cannot be sent"

    async def test_a_message_too_long_is_caught_before_its_files_are_uploaded(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        with pytest.raises(ValidationError):
            await agent.send_message("x" * 65537, attachments=[PNG])

        assert fake.traffic.seen == []

    async def test_a_chat_names_the_files_of_a_message_by_id(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        chat = agent.chat("t")
        await chat.send_message("one", attachments=[PNG])
        await chat.queue("two", attachments=[PNG, PNG])

        one, two = sent_items(fake)
        assert (one["attachments"], two["attachments"]) == (["att-1"], ["att-2", "att-3"])
        assert two["start_run"] is False

    async def test_a_new_chat_sends_its_first_message_with_its_files_and_key(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        chat = await agent.new_chat(
            "Claim", thread="t", text="first", attachments=[PNG], event_key="k", expires_at=SOON
        )

        [body] = sent_items(fake)
        assert chat.thread == "t"
        assert body == {
            "producer": {"kind": "person", "id": "u-max"},
            "kind": "chat",
            "thread": "t",
            "text": "first",
            "title": "Claim",
            "start_run": True,
            "attachments": ["att-1"],
            "event_key": "k",
            "expires_at": "2026-11-20T09:30:00Z",
        }

    async def test_an_action_can_carry_files_too(self, agent: Agent, fake: FakeIgni) -> None:
        await agent.send_item(
            "action", thread="t", action=ChatAction(op="rename", title="New"), attachments=[PNG]
        )

        [body] = sent_items(fake)
        assert (body["kind"], body["attachments"], body["action"]) == (
            "action",
            ["att-1"],
            {"op": "rename", "title": "New"},
        )


class TestAnEvent:
    async def test_it_goes_to_the_events_path_with_its_type_payload_key_and_expiry(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        await agent.send_event(
            "claim.created", {"id": "CL-1", "n": [1, 2]}, event_key="k", expires_at=SOON
        )

        [seen] = fake.traffic.requests_to(IgniPaths.SERVICE_EVENTS)
        assert seen.json_body() == {
            "producer": {"kind": "person", "id": "u-max"},
            "type": "claim.created",
            "payload": {"id": "CL-1", "n": [1, 2]},
            "event_key": "k",
            "expires_at": "2026-11-20T09:30:00Z",
        }
        assert fake.traffic.requests_to(IgniPaths.SERVICE_ITEMS) == []

    async def test_no_payload_and_an_empty_one_are_both_an_empty_object(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        await agent.send_event("a")
        await agent.send_event("b", None)
        await agent.send_event("c", {})

        bodies = [s.json_body() for s in fake.traffic.requests_to(IgniPaths.SERVICE_EVENTS)]
        assert [b["payload"] for b in bodies] == [{}, {}, {}]

    async def test_a_payload_over_65536_bytes_is_caught_and_nothing_is_sent(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        with pytest.raises(ValidationError):
            await agent.send_event("big", {"blob": "x" * 70_000})

        assert fake.traffic.seen == []

    async def test_the_same_key_is_stored_once(self, agent: Agent, fake: FakeIgni) -> None:
        first = await agent.send_event("a", event_key="k")
        again = await agent.send_event("a", event_key="k")

        assert again.duplicate and again.event_id == first.event_id


class TestAChat:
    async def test_without_a_thread_each_chat_gets_its_own_uuid_thread(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        import uuid

        first = await agent.new_chat("One")
        second = await agent.new_chat("Two")

        assert first.thread != second.thread
        for chat in (first, second):
            assert str(uuid.UUID(chat.thread.removeprefix("chat:"))) == chat.thread[5:]
        assert [b["thread"] for b in sent_items(fake)] == [first.thread, second.thread]

    async def test_a_chat_opened_without_text_sends_only_its_title(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        await agent.new_chat("Just a title", thread="t")

        [body] = sent_items(fake)
        assert "text" not in body and body["title"] == "Just a title"

    async def test_a_show_may_carry_a_title_and_a_view_is_sent_as_given(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        view = {"root": "r", "elements": {"r": {"type": "Text", "props": {"text": "Ünï"}}}}

        await agent.chat("t").show(view, title="Status", event_key="k")

        [body] = sent_items(fake)
        assert body["kind"] == "action" and body["event_key"] == "k"
        assert body["action"] == {"op": "show", "view": view, "title": "Status"}
        assert "text" not in body

    async def test_cancel_sends_the_op_alone_and_starts_no_run(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        await agent.chat("t").cancel(event_key="k")

        [body] = sent_items(fake)
        assert body["action"] == {"op": "cancel"}

    @pytest.mark.parametrize("title", ["", "t" * 201])
    async def test_a_title_igni_would_refuse_is_caught_and_nothing_is_sent(
        self, agent: Agent, fake: FakeIgni, title: str
    ) -> None:
        with pytest.raises(ValidationError):
            await agent.chat("t").rename(title)
        with pytest.raises(ValidationError):
            await agent.chat("t").show({"root": "r", "elements": {}}, title=title)

        assert fake.traffic.seen == []

    async def test_a_rename_of_exactly_two_hundred_characters_is_sent(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        await agent.chat("t").rename("é" * 200)

        assert sent_items(fake)[0]["action"] == {"op": "rename", "title": "é" * 200}

    async def test_a_chat_the_extension_may_not_open_is_refused(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        fake.agents.grants = {"messages"}

        with pytest.raises(EventRefused) as refused:
            await agent.new_chat("Claim", thread="t")

        assert refused.value.status == 403 and "service.chats" in refused.value.detail

    async def test_a_thread_over_two_hundred_characters_is_caught(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        with pytest.raises(ValidationError):
            await agent.send_message("hi", thread="t" * 201)

        assert fake.traffic.seen == []


class TestSendItem:
    async def test_an_event_kind_item_goes_to_the_items_path(
        self, agent: Agent, fake: FakeIgni
    ) -> None:
        await agent.send_item("event", text="x")

        assert [b["kind"] for b in sent_items(fake)] == ["event"]
        assert fake.traffic.requests_to(IgniPaths.SERVICE_EVENTS) == []

    async def test_two_agents_in_one_service_keep_their_own_producers(
        self, igni: IgniService, fake: FakeIgni
    ) -> None:
        host = igni.host(ORG)
        await host.agent(MAX).send_message("a")
        await host.agent(Producer.person("u-sam")).send_message("b")

        assert [b["producer"] for b in sent_items(fake)] == [
            {"kind": "person", "id": "u-max"},
            {"kind": "person", "id": "u-sam"},
        ]

    async def test_an_event_goes_to_the_producer_of_the_agent_that_sent_it(
        self, igni: IgniService, fake: FakeIgni
    ) -> None:
        await igni.host(ORG).agent(Producer.person("u-sam")).send_event("a")

        [seen] = fake.traffic.requests_to(IgniPaths.SERVICE_EVENTS)
        assert seen.json_body()["producer"] == {"kind": "person", "id": "u-sam"}
