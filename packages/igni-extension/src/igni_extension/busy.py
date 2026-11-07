"""`ext.busy`: leases that keep igni's process awake while the extension works."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from igni_extension.host_model import BusyLease, HostSelf

logger = logging.getLogger(__name__)


class BusyLeases:
    """Say this extension is working, so igni's process is not suspended under it.

    In the cloud igni's VM sleeps when nothing is busy. Work the extension
    does on its own — indexing, a sync — takes a lease for a reason; it
    expires after `ttl` seconds (default and at most 600) unless renewed
    by taking it again, so a stuck extension cannot keep the VM awake.
    """

    def __init__(self, host_self: HostSelf) -> None:
        self._host_self = host_self

    async def take(self, reason: str, ttl: float | None = None) -> BusyLease:
        """Take (or renew) the lease for `reason`."""
        return await self._host_self.busy(reason, ttl)

    async def __call__(self, reason: str, ttl: float | None = None) -> BusyLease:
        """`await ext.busy(reason, ttl)`, as igni-extension 0.1.0 spelled `take`."""
        return await self.take(reason, ttl)

    async def release(self, reason: str) -> None:
        """Let go of the lease `take` took for `reason`."""
        await self._host_self.done(reason)

    @contextlib.asynccontextmanager
    async def during(self, reason: str, ttl: float = 120.0) -> AsyncIterator[None]:
        """Busy for as long as the block runs, renewed every half `ttl`.

        async with ext.busy.during("indexing"):
            await index_everything()

        A renewal or the release that fails is logged rather than raised, so
        it never replaces what the block itself raised.
        """
        await self.take(reason, ttl)
        renewing = asyncio.get_running_loop().create_task(self._renew(reason, ttl))
        try:
            yield
        finally:
            renewing.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                try:
                    await renewing
                except Exception:
                    logger.exception("igni: could not renew the busy lease for %r", reason)
            try:
                await self.release(reason)
            except Exception:
                logger.exception("igni: could not let go of the busy lease for %r", reason)

    async def _renew(self, reason: str, ttl: float) -> None:
        while True:
            await asyncio.sleep(ttl / 2)
            await self.take(reason, ttl)
