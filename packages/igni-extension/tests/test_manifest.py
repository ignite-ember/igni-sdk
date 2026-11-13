"""`python -m igni_extension.manifest <module>`: the manifest lines the code implies."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

from igni_extension import IgniExtension
from igni_extension.manifest import ManifestLines, main

HEADER = """
from igni_extension import IgniExtension, ToolHints

READS = ToolHints(read_only=True, destructive=False, idempotent=True, open_world=False)
WRITES = ToolHints(read_only=False, destructive=True, idempotent=False, open_world=True)
"""


@pytest.fixture
def modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A directory on `sys.path` for the extension modules a test writes."""
    monkeypatch.syspath_prepend(str(tmp_path))
    before = set(sys.modules)
    yield tmp_path
    for name in set(sys.modules) - before:
        sys.modules.pop(name, None)


def write(modules: Path, name: str, body: str) -> None:
    (modules / f"{name}.py").write_text(HEADER + textwrap.dedent(body))


ONE = """
ext = IgniExtension("acme.one", environ={})

@ext.tool(hints=READS)
def lookup(slug: str) -> str:
    return slug

@ext.tool(hints=WRITES, name="close")
def close_it(slug: str) -> str:
    return slug
"""


def test_it_prints_the_id_and_every_tool_with_its_four_hints(
    modules: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(modules, "manifest_one", ONE)

    assert main(["manifest_one"]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "id": "acme.one",
        "tools": [
            {
                "name": "acme.one.close",
                "annotations": {
                    "readOnlyHint": False,
                    "destructiveHint": True,
                    "idempotentHint": False,
                    "openWorldHint": True,
                },
            },
            {
                "name": "acme.one.lookup",
                "annotations": {
                    "readOnlyHint": True,
                    "destructiveHint": False,
                    "idempotentHint": True,
                    "openWorldHint": False,
                },
            },
        ],
    }


def test_the_module_is_imported_and_its_main_is_not_run(
    modules: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        modules,
        "manifest_guarded",
        ONE
        + """
def main() -> None:
    raise SystemExit("main ran")

if __name__ == "__main__":
    main()
""",
    )

    assert main(["manifest_guarded"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "acme.one"


@pytest.mark.parametrize("argv", [[], ["a", "b"]])
def test_the_wrong_number_of_arguments_is_exit_2_with_the_usage(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv) == 2

    seen = capsys.readouterr()
    assert seen.out == ""
    assert seen.err == "usage: python -m igni_extension.manifest <module>[:attribute]\n"


def test_a_module_that_cannot_be_imported_is_exit_1(
    modules: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["manifest_not_there"]) == 1

    seen = capsys.readouterr()
    assert seen.out == ""
    assert seen.err.startswith("igni_extension.manifest: ")
    assert "manifest_not_there" in seen.err


def test_a_module_with_no_extension_is_exit_1_and_says_how_many(
    modules: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(modules, "manifest_none", "x = 1\n")

    assert main(["manifest_none"]) == 1

    err = capsys.readouterr().err
    assert "manifest_none holds 0 IgniExtension objects; name one as module:attribute" in err


TWO = """
first = IgniExtension("acme.first", environ={})
second = IgniExtension("acme.second", environ={})

@second.tool(hints=READS)
def only_second() -> str:
    return "x"

not_one = "acme"
"""


def test_a_module_with_two_extensions_needs_one_named(
    modules: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(modules, "manifest_two", TWO)

    assert main(["manifest_two"]) == 1
    assert "holds 2 IgniExtension objects" in capsys.readouterr().err


def test_module_colon_attribute_names_the_extension(
    modules: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(modules, "manifest_named", TWO)

    assert main(["manifest_named:second"]) == 0

    printed = json.loads(capsys.readouterr().out)
    assert printed["id"] == "acme.second"
    assert [tool["name"] for tool in printed["tools"]] == ["acme.second.only_second"]
    assert ManifestLines.extension_in("manifest_named:first").id == "acme.first"


@pytest.mark.parametrize("attribute", ["missing", "not_one"])
def test_an_attribute_that_is_not_an_extension_is_exit_1(
    modules: Path, capsys: pytest.CaptureFixture[str], attribute: str
) -> None:
    write(modules, "manifest_attr", TWO)

    assert main([f"manifest_attr:{attribute}"]) == 1

    assert f"manifest_attr:{attribute} is not an IgniExtension" in capsys.readouterr().err


def test_the_target_is_split_at_the_first_colon(modules: Path) -> None:
    write(modules, "manifest_colons", TWO)

    with pytest.raises(LookupError, match="manifest_colons:second:extra is not an IgniExtension"):
        ManifestLines.extension_in("manifest_colons:second:extra")


def test_lines_of_an_extension_with_no_tools_are_an_empty_list(modules: Path) -> None:
    write(modules, "manifest_empty", 'ext = IgniExtension("acme.empty", environ={})\n')

    assert ManifestLines.of("manifest_empty") == {"id": "acme.empty", "tools": []}
    assert isinstance(ManifestLines.extension_in("manifest_empty"), IgniExtension)


def test_run_as_a_module_it_exits_with_the_status_of_main(modules: Path) -> None:
    write(modules, "manifest_cli", ONE)
    env_path = str(modules)

    found = subprocess.run(
        [sys.executable, "-m", "igni_extension.manifest", "manifest_cli"],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": env_path, "PATH": ""},
    )
    missing = subprocess.run(
        [sys.executable, "-m", "igni_extension.manifest"],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": env_path, "PATH": ""},
    )

    assert found.returncode == 0 and json.loads(found.stdout)["id"] == "acme.one"
    assert missing.returncode == 2 and "usage:" in missing.stderr
