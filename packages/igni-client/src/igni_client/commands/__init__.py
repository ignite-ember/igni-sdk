"""Commands in a VM: run a shell command in a producer's microVM and stream its output.

This goes through Fleet's gateway (`POST /v1/commands`), not through
igni: the gateway wakes the VM and its node runs the command, streaming
stdout and stderr back as it is written. igni server decides who may run
what and keeps an audit record of every command.

A producer may run commands in its own VM; an org admin in any VM of
their organisation.
"""

from igni_client.commands.api import Commands
from igni_client.commands.models import (
    CommandFinished,
    CommandOutput,
    CommandRecord,
    Me,
    Wake,
)
from igni_client.commands.run import CommandRun

__all__ = [
    "CommandFinished",
    "CommandOutput",
    "CommandRecord",
    "CommandRun",
    "Commands",
    "Me",
    "Wake",
]
