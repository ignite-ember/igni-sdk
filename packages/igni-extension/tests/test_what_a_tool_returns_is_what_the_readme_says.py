"""What a tool returns reaches the model and a page as the README's table says.

Nothing said whether a tool may return a `dict`, or what a page receives
when it does; and a `list` return reaches a page not as a list but as its
items' text, one per line. The page's value is igni's reading of the
result: the text blocks joined by newlines, parsed as JSON when that is
JSON (`igni_core.extensions.service`), which `_page_value` restates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mcp.types import TextContent

from igni_extension import Caller, CallerKind, IgniExtension, ToolHints
from igni_extension.testing import HostHarness

pytestmark = pytest.mark.anyio

README = Path(__file__).resolve().parents[1] / "README.md"
READS = ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False)
ADA = Caller(kind=CallerKind.PERSON, id="u-ada", org="org-1", group="g-1")

ext = IgniExtension("acme.notes")


@ext.tool(hints=READS)
async def as_dict() -> dict[str, str]:
    return {"id": "N-42", "status": "open"}


@ext.tool(hints=READS)
async def as_json() -> str:
    return json.dumps({"id": "N-42"})


@ext.tool(hints=READS)
async def as_text() -> str:
    return "N-42 is open"


@ext.tool(hints=READS)
async def as_int() -> int:
    return 42


@ext.tool(hints=READS)
async def as_list() -> list[str]:
    return ["a", "b"]


def _page_value(texts: list[str]) -> Any:
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return joined


@pytest.mark.parametrize(
    ("tool", "model_reads", "page_gets"),
    [
        ("as_dict", None, {"id": "N-42", "status": "open"}),
        ("as_json", ['{"id": "N-42"}'], {"id": "N-42"}),
        ("as_text", ["N-42 is open"], "N-42 is open"),
        ("as_int", ["42"], 42),
        ("as_list", ["a", "b"], "a\nb"),
    ],
)
async def test_each_return_reaches_the_model_and_the_page_as_the_table_says(
    tool: str, model_reads: list[str] | None, page_gets: Any
) -> None:
    async with HostHarness(ext) as host:
        result = await host.call(tool, {}, caller=ADA)
    texts = [block.text for block in result.content if isinstance(block, TextContent)]
    assert len(texts) == len(result.content)

    if model_reads is not None:
        assert texts == model_reads
    assert _page_value(texts) == page_gets


def test_the_readme_has_the_table() -> None:
    text = README.read_text(encoding="utf-8")
    section = text[text.index("### What a tool returns") :]
    for row in ("a `dict`", "a `str` holding JSON", "any other `str`", "a `list`"):
        assert row in section
    assert "the items' text, one per line, as a string" in section
