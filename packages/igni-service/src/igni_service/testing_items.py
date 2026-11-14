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
from pydantic import BaseModel, ValidationError

from igni_service.agent_wire import AttachmentStored, ItemState, ItemStatus, ServiceItemRequest
from igni_service.events import EventAccepted, ServiceEventRequest
from igni_service.testing_item_records import ALL_GRANTS, SentEvent, Upload
from igni_service.testing_wire import DetailError


class FakeAgents:
    """igni's side of `host.agent(producer)`: the items, files and statuses a service sends.

    `fake.agents.items` is every item stored, `uploads` every file, and
    `settle(event_id, state)` plays the producer's igni taking one. Set
    `grants` to play an extension that declares less.

    Args:
        is_member: Whether a person belongs to an organisation, as the
            directory answers it: called with the organisation's id and
            the person's id.
        clock: The time now, in seconds since the epoch, as the fake's
            clock answers it.
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
        """Play the producer's igni: the item is now `state`.

        Args:
            event_id: The id of the item to move, as igni gave it when it
                accepted it.
            state: Where the item stands afterwards: `pending`,
                `delivered`, `not_handled`, `expired`, `dropped` or
                `failed`.
        """
        for index, item in enumerate(self.items):
            if item.event_id == event_id:
                self.items[index] = item.model_copy(update={"state": state})

    # ── Routes ──────────────────────────────────────────────────────

    def event(self, body: bytes, client_id: str, org_id: str) -> httpx.Response:
        """Answer `POST /v1/service-events` as igni does. Called by the fake's router.

        Args:
            body: The request's body: the JSON of a service event.
            client_id: The service that sent it.
            org_id: The organisation the service's token named.
        """
        try:
            event = ServiceEventRequest.model_validate_json(body)
        except ValidationError as exc:
            return DetailError(detail=str(exc), status=422).to_response()
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
                expires_at=event.expires_at,
                created_at=self._now(),
            ),
        )

    def item(self, body: bytes, client_id: str, org_id: str) -> httpx.Response:
        """Answer `POST /v1/service-items` as igni does. Called by the fake's router.

        Args:
            body: The request's body: the JSON of a service item.
            client_id: The service that sent it.
            org_id: The organisation the service's token named.
        """
        try:
            item = ServiceItemRequest.model_validate_json(body)
        except ValidationError as exc:
            return DetailError(detail=str(exc), status=422).to_response()
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
                expires_at=item.expires_at,
                created_at=self._now(),
            ),
        )

    def upload(
        self, *, client_id: str, filename: str, content_type: str, data: bytes
    ) -> httpx.Response:
        """Answer `POST /v1/service-attachments` as igni does. Called by the fake's router.

        Args:
            client_id: The service uploading the file.
            filename: The name the file is kept under: a file name, not a
                path.
            content_type: The media type of the bytes, as the request's
                `Content-Type` header gave it: the part before any `;`,
                and `application/octet-stream` when there is none.
            data: The bytes of the file.
        """
        if "attachments" not in self.grants:
            return self._refused("service.attachments")
        if not filename or "/" in filename or "\\" in filename:
            return DetailError(detail="filename must be a file name, not a path").to_response()
        if not data:
            return DetailError(detail="an attachment has no bytes").to_response()
        if len(data) > self.max_bytes:
            return DetailError(detail="too large", status=413).to_response()
        upload = Upload(
            attachment_id=f"att-{len(self.uploads) + 1}",
            client_id=client_id,
            filename=filename,
            content_type=content_type.split(";", 1)[0].strip() or "application/octet-stream",
            data=data,
        )
        self.uploads[upload.attachment_id] = upload
        stored = AttachmentStored(
            attachment_id=upload.attachment_id,
            filename=upload.filename,
            content_type=upload.content_type,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            expires_at=self._now() + timedelta(days=1),
        )
        return self._answer(201, stored)

    def status(self, event_id: str, client_id: str) -> httpx.Response:
        """Answer `GET /v1/service-events/{event_id}` as igni does. Called by the fake's router.

        Args:
            event_id: The id of the item to report on, as igni gave it
                when it accepted the item.
            client_id: The service asking: only its own items are
                answered.
        """
        for item in self.items:
            if item.event_id == event_id and item.client_id == client_id:
                return self._answer(200, self._status_of(item))
        return DetailError(detail="No such event from this service", status=404).to_response()

    # ── igni's rules ────────────────────────────────────────────────

    def _store(self, client_id: str, org_id: str, sent: SentEvent) -> httpx.Response:
        missing = sorted(self._needs(sent) - self.grants)
        if missing:
            return self._refused(", ".join(f"service.{grant}" for grant in missing))
        if sent.producer.kind == "person" and not self._is_member(org_id, sent.producer.id):
            return DetailError(
                detail="no such producer in this organisation", status=404
            ).to_response()
        if sent.event_key:
            for held in self.items:
                if (held.org_id, held.producer, held.event_key) == (
                    org_id,
                    sent.producer,
                    sent.event_key,
                ):
                    return self._accepted(held, duplicate=True)
        files = [self.uploads.get(a) for a in sent.attachments]
        if any(f is None or f.client_id != client_id or f.event_id is not None for f in files):
            return DetailError(detail="an attachment is not this service's").to_response()
        stored = sent.model_copy(
            update={"event_id": f"ev-{len(self.items) + 1}", "expires_at": self._expiry(sent)}
        )
        for name in sent.attachments:
            self.uploads[name] = self.uploads[name].model_copy(update={"event_id": stored.event_id})
        self.items.append(stored)
        return self._accepted(stored, duplicate=False)

    def _accepted(self, held: SentEvent, *, duplicate: bool) -> httpx.Response:
        """igni's 202 for a stored item: its id and the expiry `_store` kept for it."""
        accepted = EventAccepted(
            event_id=held.event_id, duplicate=duplicate, expires_at=held.expires_at
        )
        return self._answer(202, accepted)

    def _status_of(self, item: SentEvent) -> ItemStatus:
        """What igni reports of a stored item; `_store` always kept its expiry."""
        return ItemStatus(
            event_id=item.event_id,
            producer=item.producer,
            kind=item.kind,
            type=item.type,
            thread=item.thread,
            event_key=item.event_key,
            state=item.state,
            failed_reason="undeliverable" if item.state == "failed" else None,
            not_handled_reason=(
                f"no handler for {item.type}" if item.state == "not_handled" else None
            ),
            created_at=item.created_at,
            expires_at=item.expires_at,
            updated_at=self._now(),
        )

    @staticmethod
    def _expiry(sent: SentEvent) -> datetime:
        """What the service asked for, or igni's 14-day limit, whichever is sooner."""
        limit = sent.created_at + timedelta(days=14)
        if sent.expires_at is None:
            return limit
        asked = sent.expires_at
        if asked.tzinfo is None:
            asked = asked.replace(tzinfo=UTC)
        return min(asked, limit)

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
        return DetailError(
            detail=f"the extension does not declare {grants} in permissions.service", status=403
        ).to_response()

    @staticmethod
    def _answer(status: int, body: BaseModel) -> httpx.Response:
        """`body` as igni answers it, with `status`."""
        return httpx.Response(status, json=body.model_dump(mode="json"))

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self._clock(), UTC)


__all__ = ["ALL_GRANTS", "FakeAgents", "SentEvent", "Upload"]
