"""A producer's agent, as a service reaches it: messages, files, chats (service-identity §15).

    agent = igni.host(org_id).agent(Producer.person("u-marieke"))
    await agent.send_message(
        "Claim CL-20431 arrived; assess the damage.",
        attachments=[Attachment.from_path("damage.jpg"), Attachment.from_bytes("form.pdf", pdf)],
        thread="claim:CL-20431",
    )
    chat = await agent.new_chat("Claim CL-20431", thread="claim:CL-20431")
    await chat.show({"root": "r", "elements": {...}})   # shown, never sent to the model
    status = await agent.status(accepted.event_id)       # pending, delivered, expired, failed

Everything goes through igni server, which stores it until the
producer's igni — on their desktop, or in their Fleet VM, woken for it —
takes it, at least once, for at most 14 days. A **thread** is this
service's own key for a conversation: the first item of a thread opens a
chat for it in the producer's igni, and every later one goes there.
Without one an item goes to this extension's own chat. Nothing a service
sends lands in the chat a person has open, and nothing answers an
approval: that decision stays a person's.

What a service may send beyond a plain event is what its extension
declares in `permissions.service` — `messages`, `attachments`, `chats` —
and igni refuses the rest with `EventRefused` (403).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from igni_service.agent_wire import (
    AgentWire,
    Attachment,
    ChatAction,
    ItemKind,
    ItemStatus,
    ServiceItemRequest,
)
from igni_service.events import EventAccepted, Producer, ServiceEventRequest


class Agent:
    """One producer's agent — a person's or an app's — in one organisation.

    Args:
        org_id: The organisation the agent's items go into, as the id
            ``igni.host()`` was given.
        producer: Whose igni every item goes to: the person or the app
            the agent is for.
        wire: The wire the items go over: the calls to igni server.
    """

    def __init__(self, org_id: str, producer: Producer, wire: AgentWire) -> None:
        self._org_id = org_id
        self._producer = producer
        self._wire = wire

    @property
    def producer(self) -> Producer:
        """Whose igni this agent is: the person or app every item goes to."""
        return self._producer

    async def send_message(
        self,
        text: str,
        *,
        attachments: list[Attachment] | None = None,
        thread: str | None = None,
        title: str | None = None,
        start_run: bool = True,
        event_key: str | None = None,
        expires_at: datetime | None = None,
    ) -> EventAccepted:
        """Post `text` as this extension's message: it starts a run, or waits for the run going.

        `start_run=False` waits for the chat's next run instead. `title`
        names the chat if this message opens its thread's. Needs
        `service.messages` (and `service.attachments`, `service.chats`
        for files and a thread).

        Args:
            text: The message's words, as the agent reads them.
            attachments: The files to send with it: each is uploaded to
                igni first, and the message names it by its id.
            thread: The thread the message belongs to: the first message
                of a thread opens its chat, and every later one goes
                there. Without one the message goes to this extension's
                own chat.
            title: The chat's title, for the message that opens its
                thread's.
            start_run: Whether the message starts a run in the chat, or
                waits for the run already going.
            event_key: The key that makes a retry exact: igni stores one
                item per key and producer, so a retry after a lost reply
                is answered with the item already stored.
            expires_at: When igni stops waiting to deliver it: igni keeps
                an item for at most 14 days.
        """
        return await self.send_item(
            "message",
            text=text,
            attachments=attachments,
            thread=thread,
            title=title,
            start_run=start_run,
            event_key=event_key,
            expires_at=expires_at,
        )

    async def send_event(
        self,
        type: str,
        payload: dict[str, object] | None = None,
        *,
        event_key: str | None = None,
        expires_at: datetime | None = None,
    ) -> EventAccepted:
        """Hand this extension an event. igni posts nothing for it: the extension's handler acts.

        One no handler took reads `not_handled` (`status`). Needs no grant.

        Args:
            type: The extension's own word for what happened, as its
                handler names it: ``claim.created``.
            payload: The event's data, as the handler reads it: at most
                65536 bytes as JSON.
            event_key: The key that makes a retry exact: igni stores one
                item per key and producer, so a retry after a lost reply
                is answered with the item already stored.
            expires_at: When igni stops waiting to deliver it: igni keeps
                an item for at most 14 days.
        """
        event = ServiceEventRequest(
            producer=self._producer,
            type=type,
            payload=payload or {},
            event_key=event_key,
            expires_at=expires_at,
        )
        return await self._wire.event(self._org_id, event)

    async def new_chat(
        self,
        title: str,
        *,
        thread: str | None = None,
        text: str | None = None,
        attachments: list[Attachment] | None = None,
        event_key: str | None = None,
        expires_at: datetime | None = None,
    ) -> Chat:
        """Open a chat titled `title` — for `thread`, or a thread of its own — optionally with a first message.

        Args:
            title: The chat's title.
            thread: The thread the chat belongs to: without one, a
                thread of its own is made for it.
            text: The first message in the chat, if it should have one.
            attachments: The files to send with that first message: each
                is uploaded to igni first, and the message names it by
                its id.
            event_key: The key that makes a retry exact: igni stores one
                item per key and producer, so a retry after a lost reply
                is answered with the item already stored.
            expires_at: When igni stops waiting to deliver it: igni keeps
                an item for at most 14 days.
        """
        chat = self.chat(thread or f"chat:{uuid.uuid4()}")
        await self.send_item(
            "chat",
            text=text,
            attachments=attachments,
            thread=chat.thread,
            title=title,
            event_key=event_key,
            expires_at=expires_at,
        )
        return chat

    def chat(self, thread: str) -> Chat:
        """The chat of `thread`: opened by its first item, whichever that is.

        Args:
            thread: The thread's id: the same id names the same chat on
                every call.
        """
        return Chat(self, thread)

    async def status(self, event_id: str) -> ItemStatus:
        """Where an item igni accepted stands, as igni holds it now.

        `state` is one of:

        - `pending` — stored; the producer's igni has not taken it yet.
        - `delivered` — a message posted, or an event a handler took.
        - `not_handled` — an event no handler took: no handler for its
          type, no running extension, or the handler raised;
          `not_handled_reason` says which.
        - `expired` — not taken before `expires_at`.
        - `dropped` — the producer no longer has the extension;
          `dropped_reason` says why.
        - `failed` — the platform gave up; `failed_reason` says why.

        Raises `EventRefused` for a 4xx (an unknown `event_id`, say) and
        `IgniUnavailable` otherwise.

        Args:
            event_id: The item's id, as ``EventAccepted.event_id`` gave it.
        """
        return await self._wire.status(self._org_id, event_id)

    async def send_item(
        self,
        kind: ItemKind,
        *,
        text: str | None = None,
        attachments: list[Attachment] | None = None,
        thread: str | None = None,
        title: str | None = None,
        start_run: bool = True,
        action: ChatAction | None = None,
        event_key: str | None = None,
        expires_at: datetime | None = None,
    ) -> EventAccepted:
        """Any item: the methods above and `Chat`'s are this, spelled for one kind.

        Args:
            kind: What the item is: ``event``, ``message``, ``chat`` or
                ``action``.
            text: The item's words: the message's text, or the chat's
                first message.
            attachments: The files to send with the item: each is
                uploaded to igni first, and the item names it by its id.
            thread: The chat thread the item belongs to: the first item
                of a thread opens its chat, and every later one goes
                there.
            title: The chat's title, for the item that opens its
                thread's.
            start_run: Whether the item starts a run in the chat, or
                waits for the run already going.
            action: What an ``action`` item does to its thread's chat:
                show a view, rename it, or cancel the run working in it.
            event_key: The key that makes a retry exact: igni stores one
                item per key and producer, so a retry after a lost reply
                is answered with the item already stored.
            expires_at: When igni stops waiting to deliver it: igni keeps
                an item for at most 14 days.
        """
        item = ServiceItemRequest(
            producer=self._producer,
            kind=kind,
            thread=thread,
            text=text,
            title=title,
            start_run=start_run,
            action=action,
            attachments=[],
            event_key=event_key,
            expires_at=expires_at,
        )
        ids = await self._wire.uploaded(self._org_id, list(attachments or []))
        return await self._wire.item(self._org_id, item.model_copy(update={"attachments": ids}))


class Chat:
    """The chat of one thread in one producer's igni.

    Args:
        agent: The agent the chat's items go through: the producer's own
            agent.
        thread: The thread's id: the same id names the same chat on
            every call.
    """

    def __init__(self, agent: Agent, thread: str) -> None:
        self._agent = agent
        self.thread = thread
        """The thread's id: the same id names the same chat on every call."""

    async def send_message(
        self,
        text: str,
        *,
        attachments: list[Attachment] | None = None,
        event_key: str | None = None,
        expires_at: datetime | None = None,
    ) -> EventAccepted:
        """Post it: a run starts, or it waits for the run going.

        Args:
            text: The message's words, as the agent reads them.
            attachments: The files to send with it: each is uploaded to
                igni first, and the message names it by its id.
            event_key: The key that makes a retry exact: igni stores one
                item per key and producer, so a retry after a lost reply
                is answered with the item already stored.
            expires_at: When igni stops waiting to deliver it: igni keeps
                an item for at most 14 days.
        """
        return await self._agent.send_message(
            text,
            attachments=attachments,
            thread=self.thread,
            event_key=event_key,
            expires_at=expires_at,
        )

    async def queue(
        self,
        text: str,
        *,
        attachments: list[Attachment] | None = None,
        event_key: str | None = None,
        expires_at: datetime | None = None,
    ) -> EventAccepted:
        """For the chat's next run; starts nothing.

        Args:
            text: The message's words, held for the chat's next run.
            attachments: The files to send with it: each is uploaded to
                igni first, and the message names it by its id.
            event_key: The key that makes a retry exact: igni stores one
                item per key and producer, so a retry after a lost reply
                is answered with the item already stored.
            expires_at: When igni stops waiting to deliver it: igni keeps
                an item for at most 14 days.
        """
        return await self._agent.send_message(
            text,
            attachments=attachments,
            thread=self.thread,
            start_run=False,
            event_key=event_key,
            expires_at=expires_at,
        )

    async def show(
        self, view: dict[str, Any], *, title: str | None = None, event_key: str | None = None
    ) -> EventAccepted:
        """A json-render view in the chat — `{root, elements}` — shown, never sent to the model.

        Args:
            view: The view to show: its ``root`` and its ``elements``.
            title: The view's title.
            event_key: The key that makes a retry exact: igni stores one
                item per key and producer, so a retry after a lost reply
                is answered with the item already stored.
        """
        return await self._act(ChatAction(op="show", view=view, title=title), event_key)

    async def rename(self, title: str, *, event_key: str | None = None) -> EventAccepted:
        """Give the chat a new title (1-200 characters). Starts no run.

        Args:
            title: The chat's new title.
            event_key: The key that makes a retry exact: igni stores one
                item per key and producer, so a retry after a lost reply
                is answered with the item already stored.
        """
        return await self._act(ChatAction(op="rename", title=title), event_key)

    async def cancel(self, *, event_key: str | None = None) -> EventAccepted:
        """Stop the chat's working run. A run waiting on a person's approval is left alone.

        Args:
            event_key: The key that makes a retry exact: igni stores one
                item per key and producer, so a retry after a lost reply
                is answered with the item already stored.
        """
        return await self._act(ChatAction(op="cancel"), event_key)

    async def _act(self, action: ChatAction, event_key: str | None) -> EventAccepted:
        return await self._agent.send_item(
            "action", thread=self.thread, action=action, event_key=event_key
        )


__all__ = ["Agent", "Attachment", "Chat"]
