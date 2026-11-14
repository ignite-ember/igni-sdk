"""igni's revocations (service-identity §21), as a test publishes them.

`publish` writes a watermark: the subject's tokens issued until now stop.
The feed answers every served organisation's revocations on one cursor,
at once and never held, and 304 when nothing is new.
"""

from __future__ import annotations

import httpx

from igni_service.clock import Clock
from igni_service.revocations import Revocation, RevocationPage, RevokedKind
from igni_service.testing_wire import DetailError, RoutedCall


class FakeRevocations:
    """Every revocation igni published, in order."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.revocations: list[Revocation] = []

    def reset(self) -> None:
        self.revocations.clear()

    def publish(
        self,
        subject_id: str,
        *,
        org_id: str | None,
        kind: RevokedKind = RevokedKind.PERSON,
        reason: str = "removed",
        incarnation: str | None = None,
    ) -> Revocation:
        """Publish a watermark: ``subject_id``'s tokens issued until now stop.

        ``org_id=None`` is every organisation (a person's sessions withdrawn).
        """
        revocation = Revocation(
            kind=kind,
            org_id=org_id,
            subject_id=subject_id,
            incarnation=incarnation,
            not_before_ms=int(self.clock.wall() * 1000),
            reason=reason,
        )
        self.revocations.append(revocation)
        return revocation

    def page(self, call: RoutedCall) -> httpx.Response:
        """Every served organisation's revocations after `since` — at once, never held."""
        since = call.seen.first("since", "0") or "0"
        if not (since.isascii() and since.isdigit()):
            return DetailError(
                detail=f"since must be a cursor, not {since!r}", status=422
            ).to_response()
        cursor = str(len(self.revocations))
        if call.seen.headers.get("if-none-match") == f'"{cursor}"':
            return httpx.Response(304)
        page = RevocationPage(revocations=self.revocations[int(since) :], cursor=cursor)
        return httpx.Response(200, json=page.model_dump(mode="json"))


__all__ = ["FakeRevocations"]
