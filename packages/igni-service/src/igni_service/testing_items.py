"""`FakeIgni`'s side of the agent channel: items, files and statuses (service-identity §15).

What `FakeIgni.agents` keeps, so a service's tests can assert exactly what
reached igni: every item (`items`), every
uploaded file (`uploads`), and each item's state, which a test moves with
`settle` to play the producer's igni taking it. igni's rules are kept:
the producer must be in the organisation, an `event_key` is stored once
per producer, a file is named by one item only, and what the service may
send beyond a plain event is what its grants allow (`grants`; every grant
unless a test narrows it).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from igni_service.agent_wire import ChatAction, ItemKind, ItemState, ServiceItemRequest
from igni_service.events import Producer, ServiceEventRequest

ALL_GRANTS: frozenset[str] = frozenset({"messages", "attachments", "chats"})
"""Every grant a service's extension may declare in `permissions.service`."""


class SentEvent(BaseModel):
    """One item a service sent for a producer, as igni stored it."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    event_id: str
    """The id igni gave it."""
    org_id: str
    """The organisation the service token named."""
    client_id: str
    """The service that sent it."""
    producer: Producer
    """Whose igni it is for."""
    kind: ItemKind = "event"
    """`event`, `message`, `chat` or `action`."""
    type: str
    """An event's type; for the other kinds, the kind."""
    payload: dict[str, object] = Field(default_factory=dict)
    """An event's payload."""
    thread: str | None = None
    """The chat thread it belongs to, if any."""
    text: str | None = None
    """A message's text."""
    title: str | None = None
    """A chat's title, or an action's new one."""
    start_run: bool = True
    """Whether a message starts a run (`Chat.queue` sends `False`)."""
    action: ChatAction | None = None
    """What an `action` item does to the chat."""
    attachments: list[str] = Field(default_factory=list)
    """The ids of the files it names."""
    event_key: str | None = None
    """The key it was sent with, if any."""
    state: ItemState = "pending"
    """Where it stands; `fake.agents.settle` moves it."""
    created_at: datetime
    """When the fake stored it."""


class Upload(BaseModel):
    """One file a service uploaded."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    attachment_id: str
    """The id igni gave the file."""
    client_id: str
    """The service that uploaded it."""
    filename: str
    """Its name."""
    content_type: str
    """Its media type."""
    data: bytes
    """Its bytes."""
    event_id: str | None = None
    """The item that names it, once one does."""


class FakeAgents:
    """igni's side of `host.agent(producer)`: the items, files and statuses a service sends.

    `fake.agents.items` is every item stored, `uploads` every file, and
    `settle(event_id, state)` plays the producer's igni taking one. Set
    `grants` to play an extension that declares less.
    """

    def __init__(
        self, *, is_member: Callable[[str, str], bool], clock: Callable[[], float]
    ) -> None:
        self._is_member = is_member
        self._clock = clock
        self.items: list[SentEvent] = []
        """Every item stored, in the order it arrived."""
        self.uploads: dict[str, Upload] = {}
        """Every file uploaded, by its attachment id."""
        self.grants: set[str] = set(ALL_GRANTS)
        """What the service's extension declares in `permissions.service`."""
        self.max_bytes = 5 * 1024 * 1024
        """The largest file accepted: igni's composer limit."""

    def reset(self) -> None:
        """Forget the items and files, and grant everything again."""
        self.items.clear()
        self.uploads.clear()
        self.grants = set(ALL_GRANTS)

    def settle(self, event_id: str, state: ItemState) -> None:
        """Play the producer's igni: the item is now `state`."""
        for index, item in enumerate(self.items):
            if item.event_id == event_id:
                self.items[index] = item.model_copy(update={"state": state})

    # ── Routes ──────────────────────────────────────────────────────

    def event(self, body: bytes, client_id: str, org_id: str) -> httpx.Response:
        """Answer `POST /v1/service-events` as igni does. Called by the fake's router."""
        try:
            event = ServiceEventRequest.model_validate_json(body)
        except ValidationError as exc:
            return httpx.Response(422, json={"detail": str(exc)})
        return self._store(
            client_id,
            org_id,
            SentEvent(
                event_id="",
                org_id=org_id,
                client_id=client_id,
                producer=event.producer,
                type=event.type,
                payload=event.payload,
                event_key=event.event_key,
                created_at=self._now(),
            ),
        )

    def item(self, body: bytes, client_id: str, org_id: str) -> httpx.Response:
        """Answer `POST /v1/service-items` as igni does. Called by the fake's router."""
        try:
            item = ServiceItemRequest.model_validate_json(body)
        except ValidationError as exc:
            return httpx.Response(422, json={"detail": str(exc)})
        return self._store(
            client_id,
            org_id,
            SentEvent(
                event_id="",
                org_id=org_id,
                client_id=client_id,
                producer=item.producer,
                kind=item.kind,
                type=item.kind,
                thread=item.thread,
                text=item.text,
                title=item.title,
                start_run=item.start_run,
                action=item.action,
                attachments=item.attachments,
                event_key=item.event_key,
                created_at=self._now(),
            ),
        )

    def upload(
        self, *, client_id: str, filename: str, content_type: str, data: bytes
    ) -> httpx.Response:
        """Answer `POST /v1/service-attachments` as igni does. Called by the fake's router."""
        if "attachments" not in self.grants:
            return self._refused("service.attachments")
        if not filename or "/" in filename or "\\" in filename:
            return httpx.Response(400, json={"detail": "filename must be a file name, not a path"})
        if not data:
            return httpx.Response(400, json={"detail": "an attachment has no bytes"})
        if len(data) > self.max_bytes:
            return httpx.Response(413, json={"detail": "too large"})
        upload = Upload(
            attachment_id=f"att-{len(self.uploads) + 1}",
            client_id=client_id,
            filename=filename,
            content_type=content_type.split(";", 1)[0].strip() or "application/octet-stream",
            data=data,
        )
        self.uploads[upload.attachment_id] = upload
        return httpx.Response(
            201,
            json={
                "attachment_id": upload.attachment_id,
                "filename": upload.filename,
                "content_type": upload.content_type,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "expires_at": (self._now() + timedelta(days=1)).isoformat(),
            },
        )

    def status(self, event_id: str, client_id: str) -> httpx.Response:
        """Answer `GET /v1/service-events/{event_id}` as igni does. Called by the fake's router."""
        for item in self.items:
            if item.event_id == event_id and item.client_id == client_id:
                return httpx.Response(
                    200,
                    json={
                        "event_id": item.event_id,
                        "producer": item.producer.model_dump(),
                        "kind": item.kind,
                        "type": item.type,
                        "thread": item.thread,
                        "event_key": item.event_key,
                        "state": item.state,
                        "dropped_reason": None,
                        "failed_reason": "undeliverable" if item.state == "failed" else None,
                        "not_handled_reason": (
                            f"no handler for {item.type}" if item.state == "not_handled" else None
                        ),
                        "created_at": item.created_at.isoformat(),
                        "expires_at": (item.created_at + timedelta(days=14)).isoformat(),
                        "delivered_at": None,
                        "updated_at": self._now().isoformat(),
                    },
                )
        return httpx.Response(404, json={"detail": "No such event from this service"})

    # ── igni's rules ────────────────────────────────────────────────

    def _store(self, client_id: str, org_id: str, sent: SentEvent) -> httpx.Response:
        missing = sorted(self._needs(sent) - self.grants)
        if missing:
            return self._refused(", ".join(f"service.{grant}" for grant in missing))
        if sent.producer.kind == "person" and not self._is_member(org_id, sent.producer.id):
            return httpx.Response(404, json={"detail": "no such producer in this organisation"})
        if sent.event_key:
            for held in self.items:
                if (held.org_id, held.producer, held.event_key) == (
                    org_id,
                    sent.producer,
                    sent.event_key,
                ):
                    return httpx.Response(202, json={"event_id": held.event_id, "duplicate": True})
        files = [self.uploads.get(a) for a in sent.attachments]
        if any(f is None or f.client_id != client_id or f.event_id is not None for f in files):
            return httpx.Response(400, json={"detail": "an attachment is not this service's"})
        stored = sent.model_copy(update={"event_id": f"ev-{len(self.items) + 1}"})
        for name in sent.attachments:
            self.uploads[name] = self.uploads[name].model_copy(update={"event_id": stored.event_id})
        self.items.append(stored)
        return httpx.Response(202, json={"event_id": stored.event_id, "duplicate": False})

    @staticmethod
    def _needs(sent: SentEvent) -> set[str]:
        needed = set()
        if sent.kind == "message":
            needed.add("messages")
        if sent.kind in ("chat", "action") or sent.thread is not None:
            needed.add("chats")
        if sent.attachments:
            needed.add("attachments")
        return needed

    @staticmethod
    def _refused(grants: str) -> httpx.Response:
        return httpx.Response(
            403, json={"detail": f"the extension does not declare {grants} in permissions.service"}
        )

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self._clock(), UTC)


__all__ = ["ALL_GRANTS", "FakeAgents", "SentEvent", "Upload"]
