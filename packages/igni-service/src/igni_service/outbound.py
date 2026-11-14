"""`IgniOutbound`: every call this service makes to igni, for any organisation.

`igni.outbound.host(org_id)` — or `igni.host(org_id)` — is one
organisation's view of them: `notify`, `agent(producer)`, `send_event`,
`extension_vm_profile` and its `directory`.
"""

from __future__ import annotations

from igni_service.agent_wire import AgentWire
from igni_service.clock import Clock
from igni_service.connection import IgniConnection
from igni_service.directory import DirectoryClient
from igni_service.events import EventSender
from igni_service.host import Host
from igni_service.notifications import Notifier
from igni_service.service_tokens import ServiceTokens
from igni_service.vm_profiles import ServiceVmProfiles


class IgniOutbound:
    """The calls to igni, each made with this service's own token for the organisation.

    Args:
        connection: The service's connection to igni server: its tokens are
            issued against its registration and key.
    """

    def __init__(self, connection: IgniConnection) -> None:
        clock: Clock = connection.clock
        self.tokens = ServiceTokens(
            connection.server, connection.registration, connection.key, clock=clock
        )
        """This service's own tokens for igni, one per organisation (`ServiceTokens`)."""
        self.directory = DirectoryClient(self.tokens, clock=clock)
        """igni's directory for any organisation; `host(org_id).directory` is one organisation's."""
        self.notifier = Notifier(self.tokens)
        """Sends notifications; `host(org_id).notify` is the way to use it."""
        self.events = EventSender(self.tokens)
        """Sends events to an extension; `host(org_id).agent(producer)` is the way to use it."""
        self.agents = AgentWire(self.tokens, self.events)
        """The calls behind `Agent`: uploads, items and statuses."""
        self.vm_profiles = ServiceVmProfiles(self.tokens)
        """The extension's VM profile request; `host(org_id).extension_vm_profile()` reads it."""

    def host(self, org_id: str) -> Host:
        """igni for one organisation.

        Args:
            org_id: The organisation's id in igni, the one every call this
                host makes is for.
        """
        return Host(
            org_id,
            notifier=self.notifier,
            directory=self.directory,
            agents=self.agents,
            vm_profiles=self.vm_profiles,
        )
