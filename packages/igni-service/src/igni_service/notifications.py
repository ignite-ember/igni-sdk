"""Telling other people something, through igni server.

A service says *what happened and who it concerns*; igni works out who
that really is (recipients are resolved to active members of the
organisation, the actor is never told about their own act), stores one
delivery per person, tells each person about an `event_key` once, and
wakes their machines. The service's extension takes no part.

`Notifier` is the wire: it splits what it is given into calls igni
accepts — at most `MAX_BATCH` notifications per call and
`MAX_RECIPIENTS` recipients per notification (a longer list is sent as
several notifications with the same `event_key`, which igni still
delivers once per person) — and retries a call igni could not take.

**Retries are exact only with an `event_key`.** igni drops a repeated
`event_key` per person, so a retry after a reply that was lost on the
way back changes nothing. Without one, the same retry can tell somebody
twice.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections.abc import Awaitable, Callable, Iterable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from igni_service.errors import IgniUnavailable, NotificationRefused
from igni_service.service_tokens import ServiceTokens
from igni_service.urls import IgniPaths

logger = logging.getLogger(__name__)

MAX_KIND = 64
"""igni's limits, mirrored so a mistake is caught where it is made."""
MAX_TITLE = 200
MAX_KEY = 200
MAX_IDENTITY = 320
MAX_TARGET_PARAMS = 32
MAX_TARGET_BYTES = 2048

ParamValue = str | int | float | bool | None


class Target(BaseModel):
    """Where in the extension to go: one of its pages, and that page's params."""

    model_config = ConfigDict(frozen=True, extra="forbid", use_attribute_docstrings=True)

    page: str = Field(min_length=1, max_length=MAX_KEY)
    """The page's id, as the extension's manifest declares it."""
    params: dict[str, ParamValue] = Field(default_factory=dict, max_length=MAX_TARGET_PARAMS)
    """What the page is opened with: strings, numbers, booleans or null; small as JSON."""

    @field_validator("params")
    @classmethod
    def _small(cls, value: dict[str, ParamValue]) -> dict[str, ParamValue]:
        if any(isinstance(v, float) and not math.isfinite(v) for v in value.values()):
            raise ValueError("target params may not hold NaN or infinity: JSON has neither")
        if len(json.dumps(value)) > MAX_TARGET_BYTES:
            raise ValueError(f"target params may be at most {MAX_TARGET_BYTES} bytes as JSON")
        return value


class Notification(BaseModel):
    """One thing that happened, and who it concerns."""

    model_config = ConfigDict(frozen=True, extra="forbid", use_attribute_docstrings=True)

    kind: str = Field(min_length=1, max_length=MAX_KIND)
    """The extension's own word for what happened: `comment`, `access_requested`."""
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    """What it is about."""
    body: str = ""
    """One line. Whitespace is collapsed here; igni cuts a long one short."""
    actor: str = Field(default="", max_length=MAX_IDENTITY)
    """Who did it: a user id or an address. Never told about it."""
    target: Target | None = None
    """Where to go: one of this service's extension pages."""
    event_key: str = Field(default="", max_length=MAX_KEY)
    """The same event is delivered once per person, however often it is sent."""
    recipients: list[str] = Field(default_factory=list)
    """User ids or addresses, in this organisation."""

    @field_validator("body")
    @classmethod
    def _one_line(cls, value: str) -> str:
        return " ".join((value or "").split())

    @field_validator("recipients")
    @classmethod
    def _identities(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(r.strip() for r in value if r and r.strip()))
        too_long = [r for r in cleaned if len(r) > MAX_IDENTITY]
        if too_long:
            raise ValueError(f"a recipient may be at most {MAX_IDENTITY} characters")
        return cleaned

    def split(self, size: int) -> list[Notification]:
        """This notification with its recipients in groups of at most `size`.

        Args:
            size: The most recipients one copy may name; this notification is
                copied once for each group of them, and nothing else in it
                changes.
        """
        return [
            self.model_copy(update={"recipients": self.recipients[start : start + size]})
            for start in range(0, len(self.recipients), size)
        ]


class NotificationBatch(BaseModel):
    """`POST /v1/service-notifications`, as it goes on the wire."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    notifications: list[Notification]


class Delivered(BaseModel):
    """How many deliveries igni wrote: fewer than named is normal, not an error.

    Somebody who is not an active member, was the actor, or was already
    told about the `event_key` is not delivered to.
    """

    model_config = ConfigDict(use_attribute_docstrings=True)

    delivered: int = 0
    """How many people igni wrote a delivery for."""


Sleep = Callable[[float], Awaitable[None]]


class Notifier:
    """Sends notifications to igni for one organisation at a time.

    Args:
        tokens: This service's own tokens for igni, kept one per organisation.
        attempts: How many times a call igni did not take is tried, at least
            once.
        backoff: Seconds to wait before the second try; the wait doubles
            after every one of them.
        sleep: How the wait between tries is done: ``asyncio.sleep`` by
            default, or one that does not really wait.
    """

    MAX_BATCH = 100
    MAX_RECIPIENTS = 1000
    ATTEMPTS = 3
    """Calls per batch before giving up, and the first pause between them."""
    BACKOFF = 0.5

    def __init__(
        self,
        tokens: ServiceTokens,
        *,
        attempts: int | None = None,
        backoff: float | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._tokens = tokens
        self._attempts = max(1, attempts if attempts is not None else self.ATTEMPTS)
        self._backoff = self.BACKOFF if backoff is None else backoff
        self._sleep = sleep

    def batches(self, notifications: Iterable[Notification]) -> list[NotificationBatch]:
        """What will be sent, call by call.

        Args:
            notifications: The notifications to send; one that names nobody is
                left out, and the rest are split into as many calls as igni
                takes.
        """
        expanded = [
            part
            for notification in notifications
            if notification.recipients
            for part in notification.split(self.MAX_RECIPIENTS)
        ]
        return [
            NotificationBatch(notifications=expanded[start : start + self.MAX_BATCH])
            for start in range(0, len(expanded), self.MAX_BATCH)
        ]

    async def send(self, org_id: str, notifications: Iterable[Notification]) -> Delivered:
        """Send every notification. Raises `IgniUnavailable` or `NotificationRefused`.

        A notification with no recipients concerns nobody and is not sent.

        Args:
            org_id: The organisation the notifications are for; igni answers
                for that one only.
            notifications: The notifications to send, each naming who it
                concerns.
        """
        delivered = 0
        for batch in self.batches(notifications):
            delivered += await self._send_batch(org_id, batch)
        return Delivered(delivered=delivered)

    async def _send_batch(self, org_id: str, batch: NotificationBatch) -> int:
        body = batch.model_dump(mode="json", exclude_none=True)
        delay = self._backoff
        failure = IgniUnavailable("igni did not take the notifications")
        for attempt in range(1, self._attempts + 1):
            try:
                response = await self._tokens.request(
                    "POST", IgniPaths.NOTIFICATIONS, org_id=org_id, json=body
                )
            except IgniUnavailable as exc:
                failure = exc
            else:
                if response.status_code == 200:
                    try:
                        return Delivered.model_validate(response.json()).delivered
                    except (ValidationError, ValueError) as exc:
                        raise IgniUnavailable(
                            "igni answered the notifications with something else"
                        ) from exc
                if response.status_code != 429 and 400 <= response.status_code < 500:
                    raise NotificationRefused(response.status_code, response.text)
                failure = IgniUnavailable(f"igni answered the notifications {response.status_code}")
            if attempt < self._attempts:
                logger.warning(
                    "igni: %d notification(s) not taken (%s); retrying in %.1fs",
                    len(batch.notifications),
                    failure,
                    delay,
                )
                await self._sleep(delay)
                delay *= 2
        raise failure
