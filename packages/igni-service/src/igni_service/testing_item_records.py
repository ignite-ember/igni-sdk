"""What `FakeIgni.agents` keeps of what a service sent: its items and its files.

`SentEvent` is one item as the fake stored it and `Upload` one file;
`ALL_GRANTS` is every grant a service's extension may declare, which the
fake allows unless a test narrows it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from igni_service.agent_wire import ChatAction, ItemKind, ItemState
from igni_service.events import Producer

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
    expires_at: datetime | None = None
    """What the service asked for; the fake stores the sooner of that and the 14-day limit."""


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


__all__ = ["ALL_GRANTS", "SentEvent", "Upload"]
