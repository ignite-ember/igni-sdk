"""`igni_extension.tools`: a tool's failure in its own words, its observers, its manifest line."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from igni_extension import IgniExtension, ToolHints
from igni_extension.tools import ManifestTool, ToolFailure

READS = ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False)
WRITES = ToolHints(read_only=False, destructive=True, idempotent=False, open_world=True)


class Empty(Exception):
    pass


def test_a_tool_error_passes_through_unchanged() -> None:
    error = ToolError("no such ticket")

    assert ToolFailure.in_its_own_words(error) is error


def test_any_other_exception_becomes_a_tool_error_with_its_message() -> None:
    failure = ToolFailure.in_its_own_words(KeyError("ticket"))

    assert isinstance(failure, ToolError)
    assert str(failure) == str(KeyError("ticket"))
    assert str(ToolFailure.in_its_own_words(ValueError("bad id"))) == "bad id"


def test_an_exception_without_a_message_is_named_by_its_type() -> None:
    assert str(ToolFailure.in_its_own_words(Empty())) == "Empty"


def _ext() -> IgniExtension:
    ext = IgniExtension("acme.tickets", environ={})

    @ext.tool(hints=READS)
    async def fine(x: int) -> int:
        return x

    @ext.tool(hints=READS)
    def fine_plain(x: int) -> int:
        return x

    @ext.tool(hints=READS)
    async def fails_async() -> None:
        raise ValueError("async went wrong")

    @ext.tool(hints=READS)
    def fails_plain() -> None:
        raise ValueError("plain went wrong")

    @ext.tool(hints=READS)
    def fails_silently() -> None:
        raise Empty

    @ext.tool(hints=READS)
    def fails_as_tool_error() -> None:
        raise ToolError("said as is")

    return ext


@pytest.mark.parametrize(
    ("tool", "said"),
    [
        ("fails_async", "async went wrong"),
        ("fails_plain", "plain went wrong"),
        ("fails_silently", "Empty"),
        ("fails_as_tool_error", "said as is"),
    ],
)
async def test_a_failing_tool_tells_igni_what_went_wrong(tool: str, said: str) -> None:
    with pytest.raises(ToolError) as failed:
        await _ext().mcp.call_tool(tool, {})

    assert said in str(failed.value)


async def test_an_observer_is_entered_around_each_call_with_the_tool_name() -> None:
    ext = _ext()
    log: list[str] = []

    @contextlib.contextmanager
    def observer(tool: str) -> Iterator[None]:
        log.append(f"enter {tool}")
        try:
            yield
        finally:
            log.append(f"exit {tool}")

    with ext.tools.observing(observer):
        await ext.mcp.call_tool("fine", {"x": 1})
        await ext.mcp.call_tool("fine_plain", {"x": 1})
        with pytest.raises(ToolError):
            await ext.mcp.call_tool("fails_plain", {})

    assert log == [
        "enter fine",
        "exit fine",
        "enter fine_plain",
        "exit fine_plain",
        "enter fails_plain",
        "exit fails_plain",
    ]


async def test_observers_nest_in_the_order_given_and_leave_with_the_block() -> None:
    ext = _ext()
    log: list[str] = []

    def named(label: str):  # type: ignore[no-untyped-def]
        @contextlib.contextmanager
        def observer(tool: str) -> Iterator[None]:
            log.append(f"{label} in")
            yield
            log.append(f"{label} out")

        return observer

    with ext.tools.observing(named("a")), ext.tools.observing(named("b")):
        await ext.mcp.call_tool("fine", {"x": 1})
    await ext.mcp.call_tool("fine", {"x": 1})

    assert log == ["a in", "b in", "b out", "a out"]


async def test_an_observer_is_removed_when_its_block_raises() -> None:
    ext = _ext()
    log: list[str] = []

    @contextlib.contextmanager
    def observer(tool: str) -> Iterator[None]:
        log.append(tool)
        yield

    with pytest.raises(RuntimeError), ext.tools.observing(observer):
        raise RuntimeError

    await ext.mcp.call_tool("fine", {"x": 1})

    assert log == []


def test_the_manifest_is_empty_without_tools_and_names_none() -> None:
    ext = IgniExtension("acme.tickets", environ={})

    assert ext.tools.manifest() == []
    with pytest.raises(KeyError, match="it has: none"):
        ext.tools.names("anything")


def test_a_name_given_to_the_tool_is_the_one_in_the_manifest_and_the_names() -> None:
    ext = IgniExtension("acme.tickets", environ={})

    @ext.tool(hints=WRITES, name="close")
    def close_ticket() -> None: ...

    assert ext.tools.names("close").manifest == "acme.tickets.close"
    assert [tool.name for tool in ext.tools.manifest()] == ["acme.tickets.close"]
    with pytest.raises(KeyError, match="close_ticket"):
        ext.tools.names("close_ticket")
    assert close_ticket.manifest_name == "acme.tickets.close"  # type: ignore[attr-defined]


def test_a_manifest_entry_is_spelled_as_mcp_spells_the_hints() -> None:
    entry = ManifestTool(name="acme.tickets.close", annotations=WRITES.annotations())

    assert entry.wire() == {
        "name": "acme.tickets.close",
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    }


def test_the_manifest_lists_the_tools_sorted_by_name() -> None:
    names = [tool.name for tool in _ext().tools.manifest()]

    assert names == sorted(names) and len(names) == 6
