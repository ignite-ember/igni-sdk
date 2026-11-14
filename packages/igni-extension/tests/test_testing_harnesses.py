"""`igni_extension.testing`: `ManualClock` and `ConcurrencyHarness`, the SDK's own test aids.

Authors build their tests on these, so what they promise is pinned here
directly: a clock that moves only when told, a stall that is measured and
refused above its limit, and a caller that leaks between calls being named.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from igni_extension import Caller, IgniExtension, ToolHints
from igni_extension.caller import CallerKind
from igni_extension.testing import (
    ConcurrencyHarness,
    ConcurrencyProblem,
    ConcurrencyReport,
    ConcurrentCall,
    ManualClock,
)

READS = ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False)
ADA = Caller(kind=CallerKind.PERSON, id="u-ada")
GRACE = Caller(kind=CallerKind.PERSON, id="u-grace")


def test_a_manual_clock_starts_where_it_is_told_and_stands_still() -> None:
    assert ManualClock().monotonic() == 1_000.0
    clock = ManualClock(start=5.5)

    assert clock.monotonic() == 5.5
    assert clock.monotonic() == 5.5


def test_a_manual_clock_moves_only_by_what_it_is_advanced() -> None:
    clock = ManualClock(start=10.0)
    clock.advance(2.5)
    clock.advance(0.5)

    assert clock.monotonic() == 13.0


def _ext() -> IgniExtension:
    return IgniExtension("acme.harness", environ={})


async def test_callers_kept_apart_are_reported_clean_with_each_answer_in_order() -> None:
    ext = _ext()

    @ext.tool(hints=READS)
    async def whoami(who: str = "") -> str:
        await asyncio.sleep(0.01)
        current = Caller.current()
        return f"{who}:{current.id if current else None}"

    report = await ConcurrencyHarness(ext, stall_limit=2.0).run(
        [
            ConcurrentCall(tool="whoami", arguments={"who": "a"}, caller=ADA),
            ConcurrentCall(tool="whoami", arguments={"who": "g"}, caller=GRACE),
        ]
    )

    assert report.leaks == []
    assert [r.is_error for r in report.results] == [False, False]
    assert [r.call.caller for r in report.results] == [ADA, GRACE]
    assert "a:u-ada" in str(report.results[0].result)
    assert "g:u-grace" in str(report.results[1].result)
    assert all(r.took > 0 for r in report.results)


async def test_a_tool_that_raises_is_an_error_result_and_not_a_problem() -> None:
    ext = _ext()

    @ext.tool(hints=READS)
    async def boom() -> str:
        raise RuntimeError("no")

    report = await ConcurrencyHarness(ext, stall_limit=2.0).run(
        [ConcurrentCall(tool="boom", caller=ADA)]
    )

    assert report.results[0].is_error is True


async def test_a_call_that_blocks_the_loop_fails_the_run_naming_the_stall() -> None:
    ext = _ext()

    @ext.tool(hints=READS)
    async def blocks() -> str:
        time.sleep(0.3)
        return "done"

    harness = ConcurrencyHarness(ext, stall_limit=0.1)
    with pytest.raises(ConcurrencyProblem, match=r"event loop was held for 0\.[2-9]\d*s"):
        await harness.run([ConcurrentCall(tool="blocks", caller=ADA)])

    report = await harness.run([ConcurrentCall(tool="blocks", caller=ADA)], check=False)
    assert report.longest_stall >= 0.2


async def test_a_plain_def_tool_runs_off_the_loop_and_does_not_stall_it() -> None:
    ext = _ext()

    @ext.tool(hints=READS)
    def sleeps() -> str:
        time.sleep(0.3)
        return "done"

    report = await ConcurrencyHarness(ext, stall_limit=0.25).run(
        [ConcurrentCall(tool="sleeps", caller=ADA)]
    )

    assert report.longest_stall < 0.25


def test_check_passes_a_report_at_its_limit_and_fails_one_beyond_it() -> None:
    harness = ConcurrencyHarness(_ext(), stall_limit=0.1)

    harness.check(ConcurrencyReport(results=[], longest_stall=0.1, leaks=[]))
    with pytest.raises(ConcurrencyProblem, match="held for 0.101s"):
        harness.check(ConcurrencyReport(results=[], longest_stall=0.101, leaks=[]))


def test_check_names_every_leak_beside_a_stall() -> None:
    harness = ConcurrencyHarness(_ext(), stall_limit=0.1)

    with pytest.raises(ConcurrencyProblem) as caught:
        harness.check(
            ConcurrencyReport(results=[], longest_stall=0.5, leaks=["one leaked", "two leaked"])
        )

    text = str(caught.value)
    assert "held for 0.500s" in text
    assert text.endswith("; one leaked; two leaked")


def test_compare_notes_another_callers_and_none_but_not_the_expected_one() -> None:
    from igni_extension.caller import CallerScope

    leaks: list[str] = []
    with CallerScope.of(ADA):
        ConcurrencyHarness.compare(leaks, "t", "as it started", ADA)
        assert leaks == []
        ConcurrencyHarness.compare(leaks, "t", "as it ended", GRACE)
    ConcurrencyHarness.compare(leaks, "t", "as it started", ADA)

    assert leaks == [
        "t as it ended saw caller 'person:u-ada', but was called as 'person:u-grace'",
        "t as it started saw caller None, but was called as 'person:u-ada'",
    ]


def test_sent_index_is_minus_one_outside_a_request() -> None:
    assert ConcurrencyHarness.sent_index(ConcurrencyHarness.CALL_KEY) == -1
