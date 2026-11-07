"""`Commands`: run commands in VMs through Fleet's gateway."""

from __future__ import annotations

from igni_client.commands.models import Me
from igni_client.commands.run import CommandRun
from igni_client.commands.wire import CommandRequest, GatewayRefusal, ProducerRef
from igni_client.targets import Fleet


class Commands:
    """Run commands in VMs through Fleet's gateway."""

    def __init__(self, fleet: Fleet) -> None:
        self._fleet = fleet
        self._me: Me | None = None

    async def me(self) -> Me:
        """Who this client is to the gateway."""
        response = await self._fleet.request("GET", "/v1/me")
        if response.status_code != 200:
            raise GatewayRefusal.of(response).error()
        self._me = Me.model_validate_json(response.content)
        return self._me

    async def run(
        self, command: str, *, timeout_s: int = 600, producer: str | None = None
    ) -> CommandRun:
        """Start `command` in a VM — this producer's own unless `producer` (`kind:id`) names another.

        `timeout_s` is 1 to 3600. The command runs as root in the VM, in a shell.
        """
        CommandRequest.check(command, timeout_s)
        if producer is None:
            producer = (self._me or await self.me()).producer
        request = CommandRequest(
            producer=ProducerRef.parse(producer), command=command, timeout_s=timeout_s
        )
        return CommandRun(self._fleet, request, await self._fleet.auth.token())


__all__ = ["Commands"]
