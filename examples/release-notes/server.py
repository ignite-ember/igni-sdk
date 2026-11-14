"""The Release Notes backend.

An MCP server. igni calls its tools as ``ext.acme.notes.<tool>`` when
this extension's UI asks, and only the ones ``permissions.rpc``
grants.

State is in memory and resets when the process does, which is right
for an example: a real one would write to the workspace it was
granted (``IGNI_WORKSPACE``, here scoped to ``CHANGELOG.md`` and
``docs/**``). What is *not* simplified is the revision check — that
is the part worth copying, because a document is the one shape where
two people editing at once is normal rather than exceptional, and
"last write wins" there loses somebody's afternoon with no error.
"""

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field

#: Written by ``python server.py`` so a dev loop can find and stop it.
PID_FILE = Path("server.pid")


class Wire(BaseModel):
    """A value the UI reads: immutable, dumped by its wire names."""

    model_config = ConfigDict(frozen=True)

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True)

    @staticmethod
    def list_json(values: Sequence["Wire"]) -> str:
        """``values`` as one JSON array, each dumped the way ``to_json`` dumps it."""
        return "[" + ",".join(value.to_json() for value in values) + "]"


class Note(Wire):
    """One release's note. ``revision`` changes on every write and the
    UI sends back the one it loaded."""

    version: str
    body: str
    revision: str


class Release(Wire):
    version: str
    state: Literal["draft", "published"]
    published_at: str | None = Field(serialization_alias="publishedAt")

    def published(self, now: datetime) -> "Release":
        """This release published; a second publish keeps the first date."""
        stamp = self.published_at or now.strftime("%Y-%m-%dT%H:%M:%SZ")
        return self.model_copy(update={"state": "published", "published_at": stamp})


class Comment(Wire):
    id: str
    version: str
    author: str
    body: str
    resolved: bool


class Conflict(Wire):
    """A save refused because somebody else's revision is current."""

    conflict: str


class ReleaseNotes:
    """The in-memory store: notes by version, releases newest first, and
    the counter every saved revision is numbered from."""

    def __init__(self, notes: list[Note], releases: list[Release], comments: list[Comment]) -> None:
        self._notes = {note.version: note for note in notes}
        self._releases = list(releases)
        self._comments = list(comments)
        self._revision = 1

    @classmethod
    def example(cls) -> "ReleaseNotes":
        return cls(
            notes=[
                Note(
                    version="2.4.0",
                    body=(
                        "# 2.4.0\n\n"
                        "Extensions can now be installed from the command line.\n\n"
                        "- `igni ext init` scaffolds one that runs as written\n"
                        "- `igni ext doctor` says what is wrong before you install\n\n"
                        "```\nigni ext install ./my-extension\n```\n"
                    ),
                    revision="r1",
                ),
                Note(
                    version="2.3.1",
                    body="# 2.3.1\n\nA dead extension stops claiming to be READY.\n",
                    revision="r1",
                ),
            ],
            releases=[
                Release(version="2.4.0", state="draft", published_at=None),
                Release(version="2.3.1", state="published", published_at="2026-10-20T09:00:00Z"),
            ],
            comments=[
                Comment(
                    id="c1",
                    version="2.4.0",
                    author="Maya Okonkwo",
                    body="Worth saying the scaffold runs without edits — that is the point.",
                    resolved=False,
                ),
            ],
        )

    def releases(self) -> list[Release]:
        return list(self._releases)

    def note(self, version: str) -> Note:
        found = self._notes.get(version)
        if found is None:
            raise ToolError(f"no note for {version}")
        return found

    def comments(self, version: str) -> list[Comment]:
        return [c for c in self._comments if c.version == version]

    def save(self, version: str, body: str, revision: str) -> Note | Conflict:
        current = self.note(version)
        if current.revision != revision:
            return Conflict(conflict=current.revision)
        self._revision += 1
        saved = current.model_copy(update={"body": body, "revision": f"r{self._revision}"})
        self._notes[version] = saved
        return saved

    def publish(self, version: str, now: datetime) -> Release:
        for index, release in enumerate(self._releases):
            if release.version == version:
                self._releases[index] = release.published(now)
                return self._releases[index]
        raise ToolError(f"no release {version}")


def build_server(store: ReleaseNotes) -> MCPServer:
    """The MCP server whose five tools answer from ``store``."""
    server = MCPServer("acme-notes")

    @server.tool()
    def releases() -> str:
        """Every release, newest first."""
        return Wire.list_json(store.releases())

    @server.tool()
    def note(version: str) -> str:
        """One release's note."""
        return store.note(version).to_json()

    @server.tool()
    def comments(version: str) -> str:
        """Comments on one release."""
        return Wire.list_json(store.comments(version))

    @server.tool()
    def save(version: str, body: str, revision: str) -> str:
        """Save a draft, refusing to overwrite somebody else's.

        Answers ``{"conflict": "<their revision>"}`` rather than failing.
        A conflict is an outcome: the UI has to keep the user's text
        either way, and an exception that also carries data is a worse
        shape than a union.
        """
        return store.save(version, body, revision).to_json()

    @server.tool()
    def publish(version: str) -> str:
        """Publish a draft."""
        return store.publish(version, datetime.now(UTC)).to_json()

    return server


server = build_server(ReleaseNotes.example())


if __name__ == "__main__":
    PID_FILE.write_text(str(os.getpid()))
    server.run()
