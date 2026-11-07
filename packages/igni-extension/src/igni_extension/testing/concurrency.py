"""Many callers at once: does the extension block its loop, or mix its callers up?"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Iterator
from typing import Any

from pydantic import BaseModel

from igni_extension.caller import Caller, RequestMeta
from igni_extension.extension import IgniExtension
from igni_extension.testing.host_harness import HostHarness


class ConcurrentCall(BaseModel):
    """One call the harness makes, as one caller."""

    tool: str
    arguments: dict[str, Any] = {}
    caller: Caller


class ConcurrentResult(BaseModel):
    call: ConcurrentCall
    result: Any = None
    is_error: bool = False
    #: Seconds from sending the call to its answer.
    took: float = 0.0


class ConcurrencyReport(BaseModel):
    """What one concurrent run found."""

    results: list[ConcurrentResult]
    #: The longest the extension's event loop went without running anything
    #: else, in seconds — what a blocking call costs every other caller.
    longest_stall: float
    #: Calls during which `Caller.current()` named somebody else.
    leaks: list[str]


class ConcurrencyProblem(AssertionError):
    """The extension blocked its loop, or let one call see another's caller."""


class ConcurrencyHarness:
    """Fires calls from different callers at once, as igni does, and checks two things.

    * **Nothing blocks the loop.** One extension process serves every
      caller of its backend, on one event loop. A call that holds it — a
      sync tool's work inside an `async def`, CPU work not moved off it —
      makes every other caller wait, and a hook that waits past igni's
      deadline counts against the extension. The harness measures the
      longest stall while the calls run, and fails above `stall_limit`.
    * **Callers stay apart.** Every call carries its caller; the harness
      checks that `Caller.current()`, as each tool starts and as it ends,
      is the one that call was sent with. A caller kept in a global, or
      a scope that leaks, fails here.

        async def test_two_callers_at_once():
            report = await ConcurrencyHarness(ext).run([
                ConcurrentCall(tool="mine", caller=ada),
                ConcurrentCall(tool="mine", caller=grace),
            ])
            assert report.results[0].result != report.results[1].result

    It checks the SDK's view of the caller; what the extension does with
    it — a cache keyed by nothing, a module-level "current user" — is the
    author's to assert on the results.
    """

    #: The ticker's period, in seconds.
    TICK = 0.005
    #: The `_meta` key the harness numbers its calls with.
    CALL_KEY = "igni/test-call"

    def __init__(
        self, ext: IgniExtension, *, stall_limit: float = 0.1, timeout: float = 10.0
    ) -> None:
        self._ext = ext
        self._stall_limit = stall_limit
        self._timeout = timeout

    async def run(self, calls: list[ConcurrentCall], *, check: bool = True) -> ConcurrencyReport:
        """Make every call at once; `ConcurrencyProblem` on a stall or a leak, unless `check=False`."""
        leaks: list[str] = []
        restore = self._watch(calls, leaks)
        stalls: list[float] = []
        running = True

        async def tick() -> None:
            loop = asyncio.get_running_loop()
            while running:
                started = loop.time()
                await asyncio.sleep(self.TICK)
                stalls.append(max(0.0, loop.time() - started - self.TICK))

        try:
            async with HostHarness(self._ext, timeout=self._timeout) as host:
                ticker = asyncio.create_task(tick())
                try:
                    results = await asyncio.gather(
                        *(self._one(host, index, call) for index, call in enumerate(calls))
                    )
                finally:
                    running = False
                    await ticker
        finally:
            restore()
        report = ConcurrencyReport(
            results=list(results), longest_stall=max(stalls, default=0.0), leaks=leaks
        )
        if check:
            self.check(report)
        return report

    def check(self, report: ConcurrencyReport) -> None:
        problems: list[str] = []
        if report.longest_stall > self._stall_limit:
            problems.append(
                f"the event loop was held for {report.longest_stall:.3f}s "
                f"(limit {self._stall_limit:.3f}s): something blocks it — a sync call inside "
                "an `async def`, or CPU work not moved off the loop"
            )
        problems.extend(report.leaks)
        if problems:
            raise ConcurrencyProblem("; ".join(problems))

    async def _one(self, host: HostHarness, index: int, call: ConcurrentCall) -> ConcurrentResult:
        meta = HostHarness.request_meta(
            {Caller.META_KEY: call.caller.model_dump(mode="json"), self.CALL_KEY: index}
        )
        loop = asyncio.get_running_loop()
        started = loop.time()
        result = await host.session.call_tool(call.tool, call.arguments, meta=meta)
        took = loop.time() - started
        return ConcurrentResult(
            call=call,
            result=result.structured_content
            if result.structured_content is not None
            else result.content,
            is_error=bool(result.is_error),
            took=took,
        )

    def _watch(self, calls: list[ConcurrentCall], leaks: list[str]) -> Callable[[], None]:
        """Watch every tool call: the caller it sees, as it starts and ends, against the one sent."""
        call_key = self.CALL_KEY

        @contextlib.contextmanager
        def watched(tool: str) -> Iterator[None]:
            expected = calls[ConcurrencyHarness.sent_index(call_key)].caller
            ConcurrencyHarness.compare(leaks, tool, "as it started", expected)
            try:
                yield
            finally:
                ConcurrencyHarness.compare(leaks, tool, "as it ended", expected)

        stack = contextlib.ExitStack()
        stack.enter_context(self._ext.tools.observing(watched))
        return stack.close

    @staticmethod
    def sent_index(key: str) -> int:
        """Which of the harness's calls the request being served is."""
        meta = RequestMeta.current()
        raw = meta.get(key) if meta is not None else None
        return int(raw) if raw is not None else -1

    @staticmethod
    def compare(leaks: list[str], tool: str, when: str, expected: Caller) -> None:
        seen = Caller.current()
        if seen != expected:
            leaks.append(
                f"{tool} {when} saw caller {seen.ref if seen else None!r}, "
                f"but was called as {expected.ref!r}"
            )
