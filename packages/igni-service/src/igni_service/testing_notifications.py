"""Notifications, as igni takes them from a service and decides whom to tell.

Every call is kept as sent (`calls`); every person told, after igni's
rules, is a `Delivery` (`deliveries`). The rules: at most
`Notifier.MAX_BATCH` notifications a call and `Notifier.MAX_RECIPIENTS`
recipients each; a target page must be one the service's extension
contributes; only active members are told, never the actor; and one
`event_key` tells each person once per source.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict

from igni_service.directory import Member
from igni_service.notifications import Delivered, Notification, NotificationBatch, Notifier
from igni_service.testing_bundles import HeldExtension
from igni_service.testing_directory import FakeDirectory
from igni_service.testing_extensions import FakeExtensionStore
from igni_service.testing_wire import DetailError, RoutedCall


class NotifyCall(BaseModel):
    """One `POST /v1/service-notifications`, as the service sent it."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    org_id: str
    """The organisation the service token named."""
    client_id: str
    """The service that sent it: its client id at igni."""
    notifications: list[Notification]
    """The notifications in the call, as sent."""


class Delivery(BaseModel):
    """One person told about one notification, after igni's rules."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    org_id: str
    """The organisation the person was told in."""
    user_id: str
    """Who was told."""
    source: str
    """The extension that told them: the `id` of the bundle its service shipped, empty when it shipped none."""
    notification: Notification
    """What they were told."""


class DeliveryKey(BaseModel):
    """What igni tells a person about once: one source's one `event_key`."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    user_id: str
    source: str
    event_key: str


class FakeNotifications:
    """igni's notification endpoint, and everything it was sent and delivered."""

    def __init__(self, *, directory: FakeDirectory, extensions: FakeExtensionStore) -> None:
        self.directory = directory
        self.extensions = extensions
        self.calls: list[NotifyCall] = []
        self.deliveries: list[Delivery] = []
        self.told: set[DeliveryKey] = set()

    def reset(self) -> None:
        self.calls.clear()
        self.deliveries.clear()
        self.told.clear()

    def notify(self, call: RoutedCall) -> httpx.Response:
        """`POST /v1/service-notifications` for the organisation the token is for."""
        batch = call.seen.json_model(NotificationBatch)
        if isinstance(batch, DetailError):
            return batch.to_response()
        holder = call.holder
        shipped = self.extensions.shipped(holder.client_id)
        refused = self._refusal(batch, shipped)
        if refused is not None:
            return refused.to_response()
        self.calls.append(
            NotifyCall(
                org_id=holder.org_id,
                client_id=holder.client_id,
                notifications=batch.notifications,
            )
        )
        source = shipped.extension_id if shipped else ""
        delivered = sum(
            self._deliver(holder.org_id, source, notification)
            for notification in batch.notifications
        )
        return httpx.Response(200, json=Delivered(delivered=delivered).model_dump())

    @staticmethod
    def _refusal(batch: NotificationBatch, shipped: HeldExtension | None) -> DetailError | None:
        if len(batch.notifications) > Notifier.MAX_BATCH:
            return DetailError(detail="too many notifications in one call", status=413)
        if any(len(n.recipients) > Notifier.MAX_RECIPIENTS for n in batch.notifications):
            return DetailError(detail="too many recipients in one notification", status=413)
        if shipped is None:
            return None
        for notification in batch.notifications:
            if notification.target and notification.target.page not in shipped.pages:
                return DetailError(
                    detail=f"{notification.target.page} is not one of "
                    f"{shipped.extension_id}'s pages"
                )
        return None

    def _deliver(self, org_id: str, source: str, notification: Notification) -> int:
        """Tell everyone igni's rules allow about `notification`; how many were told."""
        actor = self.directory.member(org_id, notification.actor) if notification.actor else None
        delivered = 0
        for recipient in notification.recipients:
            member = self.directory.member(org_id, recipient)
            if member is None or not self._tells(member, actor, source, notification):
                continue
            self.deliveries.append(
                Delivery(
                    org_id=org_id, user_id=member.user_id, source=source, notification=notification
                )
            )
            delivered += 1
        return delivered

    def _tells(
        self, member: Member, actor: Member | None, source: str, notification: Notification
    ) -> bool:
        if not member.is_active:
            return False
        if actor is not None and actor.user_id == member.user_id:
            return False
        if not notification.event_key:
            return True
        once = DeliveryKey(user_id=member.user_id, source=source, event_key=notification.event_key)
        if once in self.told:
            return False
        self.told.add(once)
        return True


__all__ = ["Delivery", "DeliveryKey", "FakeNotifications", "NotifyCall"]
