"""``scripts/sync_contracts.py`` refreshes and checks the contracts copied from igni-core.

``make contracts`` runs it to copy igni-core's files over ``contracts/``;
``make contracts-check`` runs it with ``--check`` and fails on any drift. These
tests run it against a scratch igni-core and a scratch repository, so what a
developer sees — the lines it prints, the exit code, which files it writes —
is what is held.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import sync_contracts as sync


@pytest.fixture
def trees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A scratch igni-core and a scratch repository, both holding every contract."""
    core, repo = tmp_path / "igni-core", tmp_path / "igni-sdk"
    for copy, original in sync.COPIES.items():
        (core / original).parent.mkdir(parents=True, exist_ok=True)
        (core / original).write_text(f"original {original}\n", encoding="utf-8")
        (repo / copy).parent.mkdir(parents=True, exist_ok=True)
        (repo / copy).write_text(f"original {original}\n", encoding="utf-8")
    monkeypatch.setattr(sync, "CORE", core)
    monkeypatch.setattr(sync, "ROOT", repo)
    return core, repo


def drift(trees: tuple[Path, Path], copy: str, text: str = "drifted\n") -> None:
    (trees[1] / copy).write_text(text, encoding="utf-8")


def test_the_copies_are_the_four_contracts_and_the_rpc_contract_is_one() -> None:
    assert sync.COPIES == {
        "contracts/host-schema.json": "docs/host-schema.json",
        "contracts/rpc-contract.json": "docs/rpc-contract.json",
        "contracts/extension-manifest.schema.json": "docs/extension-manifest.schema.json",
        "contracts/theme.schema.json": "docs/theme.schema.json",
    }


def test_every_contract_in_the_repository_is_a_copy() -> None:
    held = {
        f"contracts/{path.name}"
        for path in (sync.ROOT / "contracts").iterdir()
        if path.suffix == ".json"
    }
    assert held == set(sync.COPIES)


def test_copies_in_sync_print_nothing_and_succeed(
    trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert sync.main([]) == 0
    assert sync.main(["--check"]) == 0
    assert capsys.readouterr().out == ""


def test_check_names_each_drifted_copy_and_fails_without_writing(
    trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    drift(trees, "contracts/rpc-contract.json")
    drift(trees, "contracts/theme.schema.json")
    assert sync.main(["--check"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "stale: contracts/rpc-contract.json",
        "stale: contracts/theme.schema.json",
    ]
    assert (trees[1] / "contracts/rpc-contract.json").read_text(encoding="utf-8") == "drifted\n"


def test_refresh_overwrites_each_drifted_copy_and_says_so(
    trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    drift(trees, "contracts/host-schema.json")
    assert sync.main([]) == 0
    assert capsys.readouterr().out == "refreshed: contracts/host-schema.json\n"
    assert (trees[1] / "contracts/host-schema.json").read_text(encoding="utf-8") == (
        "original docs/host-schema.json\n"
    )
    assert sync.main(["--check"]) == 0


def test_refresh_leaves_an_identical_copy_untouched(trees: tuple[Path, Path]) -> None:
    same = trees[1] / "contracts/theme.schema.json"
    before = same.stat().st_mtime_ns
    drift(trees, "contracts/host-schema.json")
    sync.main([])
    assert same.stat().st_mtime_ns == before


def test_a_non_ascii_contract_is_copied_exactly(trees: tuple[Path, Path]) -> None:
    text = "café — 名前 \U0001f600\n"
    (trees[0] / "docs/theme.schema.json").write_text(text, encoding="utf-8")
    sync.main([])
    assert (trees[1] / "contracts/theme.schema.json").read_bytes() == text.encode("utf-8")


def test_a_missing_local_copy_is_stale_to_check_and_is_created_by_a_refresh(
    trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    (trees[1] / "contracts/rpc-contract.json").unlink()
    assert sync.main(["--check"]) == 1
    assert capsys.readouterr().out == "stale: contracts/rpc-contract.json\n"
    assert not (trees[1] / "contracts/rpc-contract.json").exists()
    assert sync.main([]) == 0
    assert capsys.readouterr().out == "refreshed: contracts/rpc-contract.json\n"
    assert (trees[1] / "contracts/rpc-contract.json").read_text(encoding="utf-8") == (
        "original docs/rpc-contract.json\n"
    )


def test_a_missing_contracts_directory_is_made_by_a_refresh(trees: tuple[Path, Path]) -> None:
    for path in (trees[1] / "contracts").iterdir():
        path.unlink()
    (trees[1] / "contracts").rmdir()
    assert sync.main([]) == 0
    assert sorted(p.name for p in (trees[1] / "contracts").iterdir()) == sorted(
        Path(copy).name for copy in sync.COPIES
    )


@pytest.mark.parametrize("flags", [[], ["--check"]])
def test_an_original_igni_core_does_not_have_stops_with_status_2_and_says_which(
    trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str], flags: list[str]
) -> None:
    (trees[0] / "docs/rpc-contract.json").unlink()
    assert sync.main(flags) == 2
    captured = capsys.readouterr()
    assert "has no docs/rpc-contract.json" in captured.err
    assert captured.out == ""


def test_a_refresh_that_cannot_finish_writes_no_copy_at_all(trees: tuple[Path, Path]) -> None:
    """Not some copies refreshed and a failure: igni-core's incomplete set is not copied."""
    (trees[0] / "docs/theme.schema.json").unlink()
    drift(trees, "contracts/host-schema.json")
    assert sync.main([]) == 2
    assert (trees[1] / "contracts/host-schema.json").read_text(encoding="utf-8") == "drifted\n"


@pytest.mark.parametrize("flags", [[], ["--check"]])
def test_no_igni_core_checkout_is_status_2_with_the_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flags: list[str],
) -> None:
    monkeypatch.setattr(sync, "CORE", tmp_path / "nowhere")
    assert sync.main(flags) == 2
    err = capsys.readouterr().err
    assert f"no igni-core checkout at {tmp_path / 'nowhere'}" in err
    assert "IGNI_CORE_DIR" in err


def test_an_igni_core_without_docs_is_no_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync, "CORE", tmp_path)
    assert sync.main([]) == 2


def test_an_unknown_flag_is_not_a_check(trees: tuple[Path, Path]) -> None:
    drift(trees, "contracts/theme.schema.json")
    assert sync.main(["--verify"]) == 0
    assert (trees[1] / "contracts/theme.schema.json").read_text(encoding="utf-8") != "drifted\n"


def _core_from_environment(
    monkeypatch: pytest.MonkeyPatch, value: str | None, tmp_path: Path
) -> Path:
    import importlib

    if value is None:
        monkeypatch.delenv("IGNI_CORE_DIR", raising=False)
    else:
        monkeypatch.setenv("IGNI_CORE_DIR", value)
    try:
        return importlib.reload(sync).CORE
    finally:
        monkeypatch.delenv("IGNI_CORE_DIR", raising=False)
        importlib.reload(sync)


def test_igni_core_is_where_igni_core_dir_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _core_from_environment(monkeypatch, str(tmp_path), tmp_path) == tmp_path.resolve()


@pytest.mark.parametrize("value", [None, ""])
def test_igni_core_is_beside_the_repository_when_the_variable_is_unset_or_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    assert (
        _core_from_environment(monkeypatch, value, tmp_path)
        == (sync.ROOT.parent / "igni-core").resolve()
    )


def test_the_repository_s_contracts_are_in_sync_with_a_checkout_when_there_is_one() -> None:
    """``make contracts-check`` as a developer runs it: no drift, exit 0."""
    if not (sync.CORE / "docs").is_dir():
        pytest.skip(f"no igni-core checkout at {sync.CORE}")
    assert sync.main(["--check"]) == 0
