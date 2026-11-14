"""`CommandRun`: one command in a VM, its output read off the gateway's NDJSON stream."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

from igni_client.commands.models import CommandFinished, CommandOutput, CommandRecord, Wake
from igni_client.commands.wire import (
    STREAM_LINE,
    CommandAccepted,
    CommandDone,
    CommandRequest,
    GatewayRefusal,
    OutputLine,
    StreamLine,
    UnknownLine,
    VmWoken,
    _line_kind,
)
from igni_client.errors import Unavailable
from igni_client.targets import Fleet

logger = logging.getLogger(__name__)


class CommandRun:
    """A command being run. Iterate it for its output; `finished` says how it ended.

        run = igni.commands.run("pytest -q")
        async for output in run:
            print(output.text, end="")
        print(run.finished.exit_code)

    Or `await run.wait()` to collect it all.
    """

    def __init__(self, fleet: Fleet, request: CommandRequest, token: str) -> None:
        self._fleet = fleet
        self._request = request
        self._token = token
        #: igni server's record of the command, once it has accepted it.
        self.record: CommandRecord | None = None
        #: How the VM was woken for it, once it has been.
        self.woken: Wake | None = None
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
                "POST", "/v1/commands", self._token, body=self._request
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise GatewayRefusal.of(response).error()
                async for text in response.aiter_lines():
                    if not text.strip():
                        continue
                    output = self._take(text)
                    if output is not None:
                        yield output
        except httpx.HTTPError as exc:
            raise Unavailable(f"the gateway at {self._fleet.base} did not answer: {exc}") from exc
        if self.finished is None:
            self.finished = CommandFinished(error="the gateway ended the output without a result")

    def _take(self, text: str) -> CommandOutput | None:
        try:
            value = json.loads(text)
        except ValueError as exc:
            logger.warning("igni-client: passing over a line the gateway sent: %s", exc)
            return None
        if not isinstance(value, dict):
            logger.warning("igni-client: passing over a line the gateway sent: %.200s", text)
            return None
        if _line_kind(value) == "done":
            # Checked as a `CommandFinished`: a field that does not fit is raised, not passed over.
            self.finished = CommandDone.ending(value)
            return None
        line: StreamLine = STREAM_LINE.validate_python(value)
        match line:
            case CommandAccepted(command=record):
                self.record = record
            case VmWoken(woken=woken):
                self.woken = woken
            case OutputLine():
                return self._keep(line.output())
            case UnknownLine():
                pass
        return None

    def _keep(self, output: CommandOutput) -> CommandOutput:
        if output.stream == "stdout":
            self.stdout += output.text
        else:
            self.stderr += output.text
        return output


__all__ = ["CommandRun"]
