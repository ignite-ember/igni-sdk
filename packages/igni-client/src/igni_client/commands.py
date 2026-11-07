"""Commands in a VM: run a shell command in a producer's microVM and stream its output.

This goes through Fleet's gateway (`POST /v1/commands`), not through
igni: the gateway wakes the VM and its node runs the command, streaming
stdout and stderr back as it is written. igni server decides who may run
what and keeps an audit record of every command.

A producer may run commands in its own VM; an org admin in any VM of
their organisation.
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from igni_client.errors import AuthError, NotAllowed, Unavailable
from igni_client.targets import Fleet


class Me(BaseModel):
    """Who the gateway says this client is."""

    model_config = ConfigDict(extra="allow")

    #: `person:<id>`, `app:<id>` or `space:<id>`.
    producer: str
    org: str = ""
    group: str | None = None
    #: When the token this was asked with expires, in Unix seconds.
    expires_at: int = 0

    @property
    def kind(self) -> str:
        return self.producer.partition(":")[0]

    @property
    def id(self) -> str:
        return self.producer.partition(":")[2]


class CommandOutput(BaseModel):
    """A piece of a command's output, as it was written."""

    stream: Literal["stdout", "stderr"]
    data: bytes

    @property
    def text(self) -> str:
        return self.data.decode(errors="replace")


class CommandFinished(BaseModel):
    """How a command ended."""

    model_config = ConfigDict(extra="allow")

    exit_code: int | None = None
    signal: int | None = None
    timed_out: bool = False
    killed: bool = False
    duration_ms: int | None = None
    #: Why it did not run or did not finish — a VM that could not be woken
    #: (the command then runs at the VM's next wake), a cancellation, a timeout.
    error: str | None = None
    #: `False` when the output arrived in one piece at the end instead of as it was written.
    streamed: bool = True

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.error


class CommandRun:
    """A command being run. Iterate it for its output; `finished` says how it ended.

        run = igni.commands.run("pytest -q")
        async for output in run:
            print(output.text, end="")
        print(run.finished.exit_code)

    Or `await run.wait()` to collect it all.
    """

    def __init__(self, fleet: Fleet, body: dict[str, Any], token: str) -> None:
        self._fleet = fleet
        self._body = body
        self._token = token
        #: igni server's record of the command: its id, state and who asked.
        self.record: dict[str, Any] = {}
        #: How the VM was woken for it: `{"how", "node", "ms"}`.
        self.woken: dict[str, Any] = {}
        self.finished: CommandFinished | None = None
        self.stdout = ""
        self.stderr = ""
        self._started = False

    def __aiter__(self) -> AsyncIterator[CommandOutput]:
        return self._lines()

    async def wait(self) -> CommandFinished:
        """Run it to the end, keeping its output in `stdout` and `stderr`."""
        async for _ in self:
            pass
        assert self.finished is not None
        return self.finished

    async def _lines(self) -> AsyncIterator[CommandOutput]:
        if self._started:
            raise RuntimeError("a command's output can be read once")
        self._started = True
        try:
            async with self._fleet.stream(
                "POST", "/v1/commands", self._token, json=self._body
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise _refused(response)
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                    except ValueError:
                        continue
                    output = self._take(item)
                    if output is not None:
                        yield output
        except httpx.HTTPError as exc:
            raise Unavailable(f"the gateway at {self._fleet.base} did not answer: {exc}") from exc
        if self.finished is None:
            self.finished = CommandFinished(error="the gateway ended the output without a result")

    def _take(self, item: dict[str, Any]) -> CommandOutput | None:
        if "command" in item and isinstance(item["command"], dict):
            self.record = item["command"]
        elif "woken" in item and isinstance(item["woken"], dict):
            self.woken = item["woken"]
        elif item.get("done"):
            self.finished = CommandFinished.model_validate(
                {k: v for k, v in item.items() if k != "done"}
            )
        elif item.get("stream") in ("stdout", "stderr"):
            data = base64.b64decode(str(item.get("data_b64") or ""))
            output = CommandOutput(stream=item["stream"], data=data)
            if output.stream == "stdout":
                self.stdout += output.text
            else:
                self.stderr += output.text
            return output
        return None


class Commands:
    """Run commands in VMs through Fleet's gateway."""

    def __init__(self, fleet: Fleet) -> None:
        self._fleet = fleet
        self._me: Me | None = None

    async def me(self) -> Me:
        """Who this client is to the gateway."""
        response = await self._fleet.request("GET", "/v1/me")
        if response.status_code != 200:
            raise _refused(response)
        self._me = Me.model_validate(response.json())
        return self._me

    async def run(
        self, command: str, *, timeout_s: int = 600, producer: str | None = None
    ) -> CommandRun:
        """Start `command` in a VM — this producer's own unless `producer` (`kind:id`) names another.

        `timeout_s` is 1 to 3600. The command runs as root in the VM, in a shell.
        """
        if not command or len(command.encode()) > 16 * 1024:
            raise ValueError("a command is 1 byte to 16 KiB")
        if not 1 <= timeout_s <= 3600:
            raise ValueError("timeout_s is 1 to 3600")
        if producer is None:
            producer = (self._me or await self.me()).producer
        kind, _, producer_id = producer.partition(":")
        if kind not in ("person", "app", "space") or not producer_id:
            raise ValueError("a producer is 'person:<id>', 'app:<id>' or 'space:<id>'")
        body = {
            "producer": {"kind": kind, "id": producer_id},
            "command": command,
            "timeout_s": timeout_s,
        }
        return CommandRun(self._fleet, body, await self._fleet.auth.token())


def _refused(response: httpx.Response) -> Exception:
    detail = response.text.strip()
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = str(
                body.get("detail") or body.get("error_description") or body.get("error") or detail
            )
    except ValueError:
        pass
    if response.status_code == 401:
        return AuthError(f"the gateway refused the credential: {detail}")
    if response.status_code in (400, 403, 404, 422):
        return NotAllowed(f"the gateway refused: {detail}")
    return Unavailable(f"the gateway answered {response.status_code}: {detail}")


__all__ = ["CommandFinished", "CommandOutput", "CommandRun", "Commands", "Me"]
