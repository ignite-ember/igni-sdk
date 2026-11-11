"""The wire behind `Agent`: uploads, items and statuses at igni server (service-identity §15)."""

from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from igni_service.errors import EventRefused, IgniUnavailable
from igni_service.events import (
    MAX_KEY,
    EventAccepted,
    EventSender,
    Producer,
    ServiceEventRequest,
)
from igni_service.service_tokens import ServiceTokens
from igni_service.urls import IgniPaths

MAX_TEXT = 65536
"""igni's limits, mirrored so a mistake is caught where it is made."""
MAX_THREAD = 200
MAX_ATTACHMENTS = 10
MAX_TITLE = 200
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
"""What a person may attach in igni's composer."""

ItemKind = Literal["event", "message", "chat", "action"]
ItemState = Literal["pending", "delivered", "not_handled", "expired", "dropped", "failed"]


class Attachment(BaseModel):
    """A file to send with an item: any type igni's composer takes, at most 5 MiB."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    filename: str = Field(min_length=1, max_length=200)
    """The file's name, as people see it in the chat (1-200 characters)."""
    content_type: str = "application/octet-stream"
    """Its media type."""
    data: bytes = Field(min_length=1, max_length=MAX_ATTACHMENT_BYTES)
    """Its bytes: at least one, at most 5 MiB."""

    @classmethod
    def from_bytes(cls, filename: str, data: bytes, content_type: str | None = None) -> Attachment:
        """An attachment of `data`, its media type guessed from `filename` unless given.

        Args:
            filename: The file's name, as people see it in the chat (1-200
                characters); the media type is guessed from it unless one
                is given.
            data: The file's bytes: at least one, at most 5 MiB.
            content_type: The media type, when it cannot be guessed from
                the name or differs from it.
        """
        guessed = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return cls(filename=filename, content_type=guessed, data=data)

    @classmethod
    def from_path(cls, path: str | Path, content_type: str | None = None) -> Attachment:
        """The file at `path`, read now, named by its file name.

        Args:
            path: The file to read now: its name becomes the attachment's
                name.
            content_type: The media type, when it cannot be guessed from
                the file's name or differs from it.
        """
        source = Path(path)
        return cls.from_bytes(source.name, source.read_bytes(), content_type)


class AttachmentStored(BaseModel):
    """igni kept the file; an item names it by `attachment_id`."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    attachment_id: str
    """The id an item names the file by."""
    filename: str
    """Its name."""
    content_type: str
    """Its media type."""
    size: int
    """Its size in bytes."""
    sha256: str
    """Its SHA-256, hex."""
    expires_at: datetime
    """When igni deletes it if no item names it."""


class ChatAction(BaseModel):
    """What an `action` item does to its thread's chat."""

    model_config = ConfigDict(frozen=True, extra="forbid", use_attribute_docstrings=True)

    op: Literal["show", "rename", "cancel"]
    """`show` a view, `rename` the chat, or `cancel` its working run."""
    view: dict[str, Any] | None = None
    """For `show`: the json-render view, `{root, elements}`."""
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    """For `show`, the view's title; for `rename`, the chat's new title."""


class ServiceItemRequest(BaseModel):
    """`POST /v1/service-items`, as it goes on the wire."""

    model_config = ConfigDict(frozen=True, extra="forbid", use_attribute_docstrings=True)

    producer: Producer
    kind: ItemKind
    thread: str | None = Field(default=None, min_length=1, max_length=MAX_THREAD)
    text: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    start_run: bool = True
    action: ChatAction | None = None
    attachments: list[str] = Field(default_factory=list, max_length=MAX_ATTACHMENTS)
    event_key: str | None = Field(default=None, min_length=1, max_length=MAX_KEY)
    expires_at: datetime | None = None


class ItemStatus(BaseModel):
    """What became of an item: `GET /v1/service-events/{event_id}`."""

    model_config = ConfigDict(extra="ignore", use_attribute_docstrings=True)

    event_id: str
    """The item's id, as `EventAccepted.event_id` gave it."""
    producer: Producer
    """Whose igni the item was for."""
    kind: ItemKind = "event"
    """`event`, `message`, `chat` or `action`."""
    type: str
    """An event's type; for the other kinds, the kind igni recorded."""
    thread: str | None = None
    """The chat thread the item belongs to, if any."""
    event_key: str | None = None
    """The key the service sent it with, if any."""
    state: ItemState
    """Where it stands: `pending`, `delivered`, `not_handled`, `expired`,
    `dropped` or `failed` (`Agent.status` says what each means)."""
    dropped_reason: str | None = None
    """Why it was dropped, when `state` is `dropped`."""
    failed_reason: str | None = None
    """Why the platform gave up, when `state` is `failed`."""
    not_handled_reason: str | None = None
    """An event no handler took: why."""
    created_at: datetime
    """When igni stored it."""
    expires_at: datetime | None = None
    """When it stops waiting to be taken."""
    delivered_at: datetime | None = None
    """When the producer's igni took it, once it has."""
    updated_at: datetime
    """When its state last changed."""


class AgentWire:
    """The calls behind an `Agent`: uploads, items, statuses. One per service.

    Args:
        tokens: The service's own tokens for igni: every call this wire
            makes is made with them.
        sender: The wire that posts items and events, and retries them
            when igni could not take them.
    """

    def __init__(self, tokens: ServiceTokens, sender: EventSender) -> None:
        self._tokens = tokens
        self._sender = sender

    async def upload(self, org_id: str, attachment: Attachment) -> AttachmentStored:
        """Upload one file to igni, and read back what igni kept of it.

        Args:
            org_id: The organisation the file is uploaded for: the call
                is made with that organisation's token.
            attachment: The file to upload: its name, its media type and
                its bytes.
        """
        response = await self._tokens.request(
            "POST",
            IgniPaths.SERVICE_ATTACHMENTS,
            org_id=org_id,
            params={"filename": attachment.filename},
            content=attachment.data,
            headers={"Content-Type": attachment.content_type},
        )
        if response.status_code in (200, 201):
            try:
                return AttachmentStored.model_validate(response.json())
            except (ValidationError, ValueError) as exc:
                raise IgniUnavailable("igni answered the upload with something else") from exc
        if response.status_code != 429 and 400 <= response.status_code < 500:
            raise EventRefused(response.status_code, response.text)
        raise IgniUnavailable(f"igni answered the upload {response.status_code}")

    async def uploaded(self, org_id: str, attachments: list[Attachment]) -> list[str]:
        """Upload every file, and give back the ids igni named them by.

        Args:
            org_id: The organisation the files are uploaded for: the calls
                are made with that organisation's token.
            attachments: The files to upload: at most ten.
        """
        return [(await self.upload(org_id, a)).attachment_id for a in attachments]

    async def item(self, org_id: str, item: ServiceItemRequest) -> EventAccepted:
        """Post one item to igni, and read back what igni stored of it.

        Args:
            org_id: The organisation the item goes into: the call is made
                with that organisation's token.
            item: The item to post: its kind, its producer and what it
                carries.
        """
        return await self._sender.post(org_id, IgniPaths.SERVICE_ITEMS, item, what=item.kind)

    async def event(self, org_id: str, event: ServiceEventRequest) -> EventAccepted:
        """Send one event to igni, and read back what igni stored of it.

        Args:
            org_id: The organisation the event goes into: the call is made
                with that organisation's token.
            event: The event to send: its producer, its type and its
                payload.
        """
        return await self._sender.send(org_id, event)

    async def status(self, org_id: str, event_id: str) -> ItemStatus:
        """Read where one item stands, as igni holds it now.

        Args:
            org_id: The organisation the item belongs to: the call is made
                with that organisation's token.
            event_id: The item's id, as ``EventAccepted.event_id`` gave it.
        """
        response = await self._tokens.request(
            "GET", IgniPaths.service_event(event_id), org_id=org_id
        )
        if response.status_code == 200:
            try:
                return ItemStatus.model_validate(response.json())
            except (ValidationError, ValueError) as exc:
                raise IgniUnavailable("igni answered the status with something else") from exc
        if 400 <= response.status_code < 500:
            raise EventRefused(response.status_code, response.text)
        raise IgniUnavailable(f"igni answered the status {response.status_code}")


__all__ = [
    "AgentWire",
    "Attachment",
    "AttachmentStored",
    "ChatAction",
    "ItemKind",
    "ItemState",
    "ItemStatus",
    "ServiceItemRequest",
]
