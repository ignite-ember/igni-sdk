"""The README says a lockfile target's standing is known only once the client opens.

Concepts presented `Local(project_dir=...).standing` as `"program"`; before
`IgniClient` opens, it is `"unknown"`, because the lockfile is read at open.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from igni_client import IgniClient, Local
from igni_client.testing import FakeIgni

README = Path(__file__).resolve().parents[1] / "README.md"


@pytest.fixture(autouse=True)
def _no_approver_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IGNI_APPROVER_TOKEN", raising=False)


async def test_the_standing_the_readme_gives_before_and_after_open_is_the_target_s(
    tmp_path: Path,
) -> None:
    async with FakeIgni(local_token="program") as fake:
        (tmp_path / ".igni").mkdir()
        lockfile = {"pid": 1, "port": fake.socket.port, "ws_token": "program", "created_at": 0}
        (tmp_path / ".igni" / "backend.lock").write_text(json.dumps(lockfile))
        target = Local(project_dir=tmp_path)
        before = target.standing
        async with IgniClient(target):
            after = target.standing

    text = " ".join(README.read_text(encoding="utf-8").split())
    assert (before, after) == ("unknown", "program")
    assert f'`standing` is `"{after}"` once the client is open' in text
    assert f'until then its `standing` is `"{before}"`' in text
