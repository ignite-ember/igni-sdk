"""The release-notes example's backend does what its README and UI rely on.

``examples/release-notes/server.py`` is an MCP server; the extension's UI
calls its five tools. These tests call them through the server's own tool
dispatch (and once over real stdio, the way the manifest's dev command
starts it), against a fresh copy of the module each time, because the
store its ``server`` answers from is built at import and kept in memory.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server.mcpserver.exceptions import ToolError

SERVER = Path(__file__).resolve().parent.parent / "examples" / "release-notes" / "server.py"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def notes(tmp_path, monkeypatch):
    """A fresh import of the server, in an empty cwd."""
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("release_notes_server", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def call(module, tool, **arguments):
    result = await module.server.call_tool(tool, arguments)
    return json.loads(result.content[0].text)


@pytest.mark.anyio
async def test_releases_lists_every_release_newest_first(notes):
    got = await call(notes, "releases")
    assert [(r["version"], r["state"]) for r in got] == [
        ("2.4.0", "draft"),
        ("2.3.1", "published"),
    ]


@pytest.mark.anyio
async def test_the_server_exposes_exactly_the_five_tools(notes):
    names = {t.name for t in await notes.server.list_tools()}
    assert names == {"releases", "note", "comments", "save", "publish"}


@pytest.mark.anyio
async def test_note_returns_version_body_and_revision(notes):
    got = await call(notes, "note", version="2.3.1")
    assert got["version"] == "2.3.1"
    assert got["revision"] == "r1"
    assert got["body"].startswith("# 2.3.1")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("note", {"version": "9.9.9"}),
        ("save", {"version": "9.9.9", "body": "x", "revision": "r1"}),
        ("publish", {"version": "9.9.9"}),
        ("note", {"version": ""}),
    ],
)
async def test_an_unknown_version_is_a_tool_error_naming_it(notes, tool, arguments):
    with pytest.raises(ToolError, match=re.escape(arguments["version"] or "no ")):
        await call(notes, tool, **arguments)


@pytest.mark.anyio
async def test_comments_are_filtered_by_version(notes):
    got = await call(notes, "comments", version="2.4.0")
    assert [c["id"] for c in got] == ["c1"]
    assert await call(notes, "comments", version="2.3.1") == []
    assert await call(notes, "comments", version="nope") == []


@pytest.mark.anyio
async def test_save_with_the_current_revision_stores_the_body_and_bumps_it(notes):
    saved = await call(notes, "save", version="2.4.0", body="new text", revision="r1")
    assert saved["body"] == "new text"
    assert saved["revision"] != "r1"
    assert (await call(notes, "note", version="2.4.0")) == saved


@pytest.mark.anyio
async def test_save_with_a_stale_revision_answers_conflict_and_keeps_the_body(notes):
    first = await call(notes, "save", version="2.4.0", body="mine", revision="r1")
    second = await call(notes, "save", version="2.4.0", body="theirs", revision="r1")
    assert second == {"conflict": first["revision"]}
    assert (await call(notes, "note", version="2.4.0"))["body"] == "mine"


@pytest.mark.anyio
async def test_save_with_an_empty_revision_is_a_conflict_not_an_error(notes):
    got = await call(notes, "save", version="2.3.1", body="x", revision="")
    assert got == {"conflict": "r1"}
    assert (await call(notes, "note", version="2.3.1"))["body"].startswith("# 2.3.1")


@pytest.mark.anyio
async def test_revisions_are_unique_across_versions_and_body_is_stored_as_is(notes):
    body = "héllo 🚀\n" + "x" * 100_000
    a = await call(notes, "save", version="2.4.0", body=body, revision="r1")
    b = await call(notes, "save", version="2.3.1", body="", revision="r1")
    assert a["body"] == body
    assert b["body"] == ""
    assert a["revision"] != b["revision"]


@pytest.mark.anyio
async def test_publish_marks_the_release_published_and_dates_it(notes):
    got = await call(notes, "publish", version="2.4.0")
    assert got["state"] == "published"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", got["publishedAt"])
    listed = {r["version"]: r for r in await call(notes, "releases")}
    assert listed["2.4.0"] == got


@pytest.mark.anyio
async def test_publishing_twice_keeps_the_first_publication_date(notes):
    already = await call(notes, "publish", version="2.3.1")
    assert already["publishedAt"] == "2026-10-20T09:00:00Z"
    first = await call(notes, "publish", version="2.4.0")
    assert await call(notes, "publish", version="2.4.0") == first


def test_importing_writes_nothing_only_running_it_writes_the_pid_file(notes, tmp_path):
    assert not (tmp_path / "server.pid").exists()


@pytest.mark.anyio
async def test_each_store_keeps_its_own_state(notes):
    one, two = notes.ReleaseNotes.example(), notes.ReleaseNotes.example()
    one.save("2.4.0", "mine", "r1")
    assert two.note("2.4.0").revision == "r1"
    other = notes.build_server(two)
    got = json.loads((await other.call_tool("note", {"version": "2.4.0"})).content[0].text)
    assert got["revision"] == "r1"


@pytest.mark.anyio
async def test_the_dev_command_serves_the_tools_over_stdio(tmp_path):
    manifest = json.loads((SERVER.parent / "manifest.json").read_text())
    command = manifest["dev"]["command"]
    assert command == ["python", "server.py"]
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], cwd=tmp_path)
    with anyio.fail_after(60):
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == {
                "releases",
                "note",
                "comments",
                "save",
                "publish",
            }
            bad = await session.call_tool("note", {"version": "0.0.0"})
            assert bad.is_error
            assert "no note for 0.0.0" in bad.content[0].text
    assert (tmp_path / "server.pid").read_text().isdigit()
