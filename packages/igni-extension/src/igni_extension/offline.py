"""`ext.host` for a process igni gave no socket to.

Started without `IGNI_HOST_URL` and `IGNI_HOST_SECRET` — run outside igni,
or under `testing.HostHarness`, which speaks only MCP — `ext.host` raises
`NotConfigured`, except `ext.host.notifications.notify`: igni reads that
from the MCP session too (`notifications/igni/notify`), so it travels
there.
"""

from __future__ import annotations

from typing import Any

from igni_extension.errors import NotConfigured
from igni_extension.notifications import LocalNotification, NotifyNotification
from igni_extension.session import HostSession


class OfflineHost:
    """A `HostLink` with no socket behind it: notify goes over MCP, the rest refuses."""

    NOTIFY = "notifications.notify"
    """The one member that works without the socket."""

    def __init__(self, session: HostSession) -> None:
        self._session = session

    async def request(
        self,
        op: str,
        path: str,
        *,
        window: str | None = None,
        session: str | None = None,
        params: dict[str, Any] | None = None,
        value: Any = None,
    ) -> Any:
        if op == "call" and path == self.NOTIFY:
            notification = LocalNotification.model_validate((params or {})["notification"])
            await self._session.send(NotifyNotification.of(notification))
            return None
        raise NotConfigured(
            f"host.{path}: igni did not give this process the host's address "
            "(IGNI_HOST_URL, IGNI_HOST_SECRET) — it is not running inside igni"
        )


__all__ = ["OfflineHost"]
