"""``scripts/check_npm_consumers.py`` fails for the right reasons.

``test_the_npm_packages_resolve.py`` runs the whole check once, against the real
packages, and holds that it passes. A check that only ever passes proves
nothing, so these tests give each step something broken — a tarball missing
what its manifest names, types read from the source, a package that does not
export what a consumer needs — and hold that it says so, in a
``ConsumerError`` that ``main`` prints as ``FAIL <reason>`` with status 1. The
compiler, ``npm`` and Node are stand-ins where the step is about what it does
with their answers, and Node itself where the step is about Node.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import stat
import tarfile
from pathlib import Path

import pytest

from scripts import check_npm_consumers as cnc

REAL_ROOT = cnc.ROOT
SCOPE = json.loads((REAL_ROOT / cnc.PACKAGES[0] / "package.json").read_text(encoding="utf-8"))[
    "name"
].split("/")[0]


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scratch repository with the two packages' manifests, and its own scratch dir."""
    for package in cnc.PACKAGES:
        (tmp_path / package).mkdir(parents=True)
        (tmp_path / package / "package.json").write_text(
            json.dumps(
                {
                    "name": f"{SCOPE}/{Path(package).name}",
                    "main": "./dist/index.js",
                    "types": "./dist/index.d.ts",
                    "exports": {
                        ".": {
                            "types": "./dist/index.d.ts",
                            "node": "./dist/index.js",
                            "default": "./src/index.ts",
                        },
                        "./extra": {"types": "./dist/extra.d.ts", "node": "./dist/extra.js"},
                    },
                }
            ),
            encoding="utf-8",
        )
    monkeypatch.setattr(cnc, "ROOT", tmp_path)
    monkeypatch.setattr(cnc, "SCRATCH", tmp_path / ".tmp" / "npm-consumer")
    return tmp_path


def program(directory: Path, name: str, stdout: str = "", stderr: str = "", code: int = 0) -> Path:
    """An executable called ``name`` that prints and exits as told, and logs its arguments."""
    directory.mkdir(parents=True, exist_ok=True)
    out, err = directory / f"{name}.out", directory / f"{name}.err"
    out.write_text(stdout)
    err.write_text(stderr)
    path = directory / name
    path.write_text(
        f'#!/bin/sh\necho "$@" > "{directory}/{name}.args"\ncat "{out}"\ncat "{err}" >&2\nexit {code}\n'
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def only_on_path(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}/usr/bin{os.pathsep}/bin")


def tarball(path: Path, members: dict[str, str]) -> Path:
    """A tarball holding ``members`` (name -> text), the names exactly as given."""
    with tarfile.open(path, "w:gz") as archive:
        for name, text in members.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return path


FULL = {
    "package/package.json": "{}",
    "package/dist/index.js": "",
    "package/dist/index.d.ts": "",
    "package/dist/extra.js": "",
    "package/dist/extra.d.ts": "",
    "package/src/index.ts": "",
}

# ── tarball_contents and install ──────────────────────────────────────────────


def test_a_tarball_s_contents_are_its_paths_without_the_package_prefix(tmp_path: Path) -> None:
    archive = tarball(
        tmp_path / "a.tgz",
        {"package/dist/a.js": "", "package/package.json": "", "elsewhere/b.js": "", "c.js": ""},
    )
    assert cnc.tarball_contents(archive) == {"dist/a.js", "package.json"}


def test_install_unpacks_a_package_under_its_manifest_name_without_the_prefix(
    root: Path, tmp_path: Path
) -> None:
    package = cnc.PACKAGES[0]
    archive = tarball(
        tmp_path / "a.tgz",
        {"package/dist/index.js": "export {}", "package/package.json": "{}", "stray.txt": "x"},
    )
    consumer = tmp_path / "consumer"
    cnc.install({package: archive}, consumer)
    base = consumer / "node_modules" / SCOPE / Path(package).name
    assert sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()) == [
        "dist/index.js",
        "package.json",
    ]
    assert (base / "dist/index.js").read_text() == "export {}"


def test_install_refuses_a_member_that_would_leave_the_package(root: Path, tmp_path: Path) -> None:
    archive = tarball(tmp_path / "a.tgz", {"package/../../escape.txt": "x"})
    with pytest.raises(tarfile.FilterError):
        cnc.install({cnc.PACKAGES[0]: archive}, tmp_path / "consumer")
    assert not (tmp_path / "escape.txt").exists()


# ── check_the_build_is_in_the_tarball ─────────────────────────────────────────


def test_a_tarball_carrying_everything_the_manifest_names_passes(
    root: Path, tmp_path: Path
) -> None:
    cnc.check_the_build_is_in_the_tarball(cnc.PACKAGES[0], tarball(tmp_path / "a.tgz", FULL))


def test_a_tarball_missing_a_manifest_target_fails_naming_it(root: Path, tmp_path: Path) -> None:
    members = {k: v for k, v in FULL.items() if k != "package/dist/extra.js"}
    with pytest.raises(cnc.ConsumerError, match=r"does not carry \['./dist/extra.js'\]"):
        cnc.check_the_build_is_in_the_tarball(cnc.PACKAGES[0], tarball(tmp_path / "a.tgz", members))


def test_a_tarball_missing_the_main_file_fails(root: Path, tmp_path: Path) -> None:
    members = {k: v for k, v in FULL.items() if k != "package/dist/index.js"}
    with pytest.raises(cnc.ConsumerError, match="dist/index.js"):
        cnc.check_the_build_is_in_the_tarball(cnc.PACKAGES[0], tarball(tmp_path / "a.tgz", members))


def test_a_tarball_with_no_build_fails_even_when_the_manifest_names_only_source(
    root: Path, tmp_path: Path
) -> None:
    path = root / cnc.PACKAGES[0] / "package.json"
    path.write_text(
        json.dumps({"main": "./src/index.ts", "types": "./src/index.ts", "exports": {}}),
        encoding="utf-8",
    )
    archive = tarball(tmp_path / "a.tgz", {"package/src/index.ts": ""})
    with pytest.raises(cnc.ConsumerError, match="carries no build"):
        cnc.check_the_build_is_in_the_tarball(cnc.PACKAGES[0], archive)


def test_a_target_under_a_nested_condition_must_be_in_the_tarball_too(
    root: Path, tmp_path: Path
) -> None:
    path = root / cnc.PACKAGES[0] / "package.json"
    path.write_text(
        json.dumps(
            {
                "main": "./dist/index.js",
                "types": "./dist/index.d.ts",
                "exports": {
                    ".": {"import": {"types": "./dist/index.d.ts", "default": "./dist/deep.js"}}
                },
            }
        ),
        encoding="utf-8",
    )
    members = {"package/dist/index.js": "", "package/dist/index.d.ts": ""}
    with pytest.raises(cnc.ConsumerError, match="dist/deep.js"):
        cnc.check_the_build_is_in_the_tarball(cnc.PACKAGES[0], tarball(tmp_path / "a.tgz", members))


def test_exports_may_be_a_single_path(root: Path, tmp_path: Path) -> None:
    path = root / cnc.PACKAGES[0] / "package.json"
    path.write_text(
        json.dumps({"main": "./dist/a.js", "types": "./dist/a.d.ts", "exports": "./dist/a.js"}),
        encoding="utf-8",
    )
    members = {"package/dist/a.js": "", "package/dist/a.d.ts": ""}
    cnc.check_the_build_is_in_the_tarball(cnc.PACKAGES[0], tarball(tmp_path / "a.tgz", members))


@pytest.mark.parametrize("key", ["main", "types", "exports"])
def test_a_manifest_without_main_types_or_exports_is_a_consumer_error(
    root: Path, tmp_path: Path, key: str
) -> None:
    path = root / cnc.PACKAGES[0] / "package.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    del manifest[key]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(cnc.ConsumerError, match=f"{cnc.PACKAGES[0]}'s package.json has no .*{key}"):
        cnc.check_the_build_is_in_the_tarball(cnc.PACKAGES[0], tarball(tmp_path / "a.tgz", FULL))


# ── build and pack ────────────────────────────────────────────────────────────


def test_a_package_that_does_not_compile_fails_with_the_compiler_s_words(root: Path) -> None:
    program(root / "node_modules" / ".bin", "tsc", stdout="error TS2305: no export", code=2)
    with pytest.raises(cnc.ConsumerError, match=f"(?s){cnc.PACKAGES[0]} does not build.*TS2305"):
        cnc.build()


def test_each_package_is_compiled_with_its_own_build_config(root: Path) -> None:
    bin_dir = root / "node_modules" / ".bin"
    program(bin_dir, "tsc")
    cnc.build()
    assert (bin_dir / "tsc.args").read_text().split() == [
        "-p",
        f"{cnc.PACKAGES[-1]}/tsconfig.build.json",
    ]


def test_pack_names_each_package_s_tarball_in_the_destination(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program(tmp_path / "bin", "npm", stdout="notice\nthe-package-1.0.0.tgz\n")
    only_on_path(monkeypatch, tmp_path / "bin")
    assert cnc.pack(tmp_path / "out") == {
        package: tmp_path / "out" / "the-package-1.0.0.tgz" for package in cnc.PACKAGES
    }


def test_a_package_npm_cannot_pack_fails_with_npm_s_words(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program(tmp_path / "bin", "npm", stderr="npm ERR! no files", code=1)
    only_on_path(monkeypatch, tmp_path / "bin")
    with pytest.raises(cnc.ConsumerError, match=f"(?s){cnc.PACKAGES[0]} does not pack.*no files"):
        cnc.pack(tmp_path / "out")


def test_npm_naming_no_tarball_is_a_consumer_error(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program(tmp_path / "bin", "npm", stdout="")
    only_on_path(monkeypatch, tmp_path / "bin")
    with pytest.raises(cnc.ConsumerError, match="named no tarball"):
        cnc.pack(tmp_path / "out")


def test_a_tool_that_is_not_installed_is_a_consumer_error_that_names_it(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    with pytest.raises(cnc.ConsumerError, match="cannot run npm"):
        cnc.pack(tmp_path / "out")
    with pytest.raises(cnc.ConsumerError, match="cannot run .*tsc"):
        cnc.build()


# ── typecheck ─────────────────────────────────────────────────────────────────


def resolved(package: str, where: str) -> str:
    return (
        f"======== Module name '{SCOPE}/{package}' was successfully resolved to '{where}'. ========"
    )


def trace(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def test_a_consumer_that_reads_both_packages_from_the_build_passes(
    root: Path, tmp_path: Path
) -> None:
    program(
        root / "node_modules" / ".bin",
        "tsc",
        stdout=trace(
            resolved("extension-bridge", "/c/node_modules/pkg/dist/index.d.ts"),
            resolved("ui-react", "/c/node_modules/pkg/dist/index.d.ts"),
        ),
    )
    cnc.typecheck(tmp_path)


def test_a_consumer_that_does_not_type_check_fails_with_the_compiler_s_words(
    root: Path, tmp_path: Path
) -> None:
    program(root / "node_modules" / ".bin", "tsc", stdout="TS2305: no export 'connect'", code=2)
    with pytest.raises(cnc.ConsumerError, match="(?s)cannot type-check.*TS2305"):
        cnc.typecheck(tmp_path)


@pytest.mark.parametrize("missing", ["extension-bridge", "ui-react"])
def test_a_package_that_did_not_resolve_at_all_fails(
    root: Path, tmp_path: Path, missing: str
) -> None:
    lines = [
        resolved(package, "/c/dist/index.d.ts")
        for package in ("extension-bridge", "ui-react")
        if package != missing
    ]
    program(root / "node_modules" / ".bin", "tsc", stdout=trace(*lines))
    with pytest.raises(cnc.ConsumerError, match=f"did not resolve {SCOPE}/{missing}"):
        cnc.typecheck(tmp_path)


@pytest.mark.parametrize("source", ["extension-bridge", "ui-react"])
def test_types_read_from_the_source_fail_even_though_the_compiler_passed(
    root: Path, tmp_path: Path, source: str
) -> None:
    lines = [
        resolved(package, "/c/node_modules/pkg/src/index.ts")
        if package == source
        else resolved(package, "/c/node_modules/pkg/dist/index.d.ts")
        for package in ("extension-bridge", "ui-react")
    ]
    program(root / "node_modules" / ".bin", "tsc", stdout=trace(*lines))
    with pytest.raises(cnc.ConsumerError, match=f"{SCOPE}/{source} from the source"):
        cnc.typecheck(tmp_path)


def test_one_resolution_from_the_source_is_enough_to_fail(root: Path, tmp_path: Path) -> None:
    program(
        root / "node_modules" / ".bin",
        "tsc",
        stdout=trace(
            resolved("extension-bridge", "/c/dist/index.d.ts"),
            resolved("extension-bridge", "/c/src/protocol.ts"),
            resolved("ui-react", "/c/dist/index.d.ts"),
        ),
    )
    with pytest.raises(cnc.ConsumerError, match="from the source"):
        cnc.typecheck(tmp_path)


# ── run_it, with Node ─────────────────────────────────────────────────────────

GOOD = {
    "extension-bridge": "export const connect = () => {}; export class HostError extends Error {}",
    "extension-bridge/protocol": "export const BRIDGE_VERSION = 1;",
    "extension-bridge/tokens": "export const applyThemeTokens = () => {};",
    "ui-react": "export const Button = () => null;",
}


def consumer_with(base: Path, modules: dict[str, str]) -> Path:
    """A consumer whose node_modules hold ``modules``, named as the program imports them."""
    consumer = base / "consumer"
    for name, source in modules.items():
        package, _, sub = name.partition("/")
        folder = consumer / "node_modules" / SCOPE / package
        folder.mkdir(parents=True, exist_ok=True)
        entry = f"{sub}.js" if sub else "index.js"
        (folder / entry).write_text(source, encoding="utf-8")
        manifest = folder / "package.json"
        exports = json.loads(manifest.read_text()) if manifest.exists() else {"exports": {}}
        exports["name"] = f"{SCOPE}/{package}"
        exports["type"] = "module"
        exports["exports"]["./" + sub if sub else "."] = "./" + entry
        manifest.write_text(json.dumps(exports), encoding="utf-8")
    (consumer / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    return consumer


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


@needs_node
def test_packages_that_export_what_a_consumer_needs_run(tmp_path: Path) -> None:
    cnc.run_it(consumer_with(tmp_path, GOOD))


@needs_node
@pytest.mark.parametrize(
    "module, source, complaint",
    [
        ("extension-bridge", "export class HostError extends Error {}", "does not export connect"),
        ("extension-bridge", "export const connect = () => {}", "does not export HostError"),
        ("extension-bridge/protocol", "export const BRIDGE_VERSION = '1';", "no wire version"),
        ("extension-bridge/protocol", "export {}", "no wire version"),
        ("extension-bridge/tokens", "export const applyThemeTokens = 1;", "no tokens"),
        ("ui-react", "export const Button = {};", "no components"),
    ],
)
def test_a_package_missing_or_mistyping_an_export_fails_the_run(
    tmp_path: Path, module: str, source: str, complaint: str
) -> None:
    modules = {**GOOD, module: source}
    with pytest.raises(cnc.ConsumerError, match=f"(?s)cannot run the packages.*{complaint}"):
        cnc.run_it(consumer_with(tmp_path, modules))


@needs_node
def test_a_package_that_cannot_be_imported_fails_the_run(tmp_path: Path) -> None:
    modules = {k: v for k, v in GOOD.items() if k != "ui-react"}
    with pytest.raises(cnc.ConsumerError, match="cannot run the packages"):
        cnc.run_it(consumer_with(tmp_path, modules))


# ── check and main ────────────────────────────────────────────────────────────


def test_main_prints_fail_and_the_reason_to_stderr_and_returns_1(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    program(root / "node_modules" / ".bin", "tsc", stdout="TS2305", code=2)
    assert cnc.main() == 1
    captured = capsys.readouterr()
    assert captured.err.startswith(f"FAIL {cnc.PACKAGES[0]} does not build")
    assert captured.out == ""


def test_check_starts_from_an_empty_scratch_directory(root: Path) -> None:
    leftover = cnc.SCRATCH / "consumer" / "old.txt"
    leftover.parent.mkdir(parents=True)
    leftover.write_text("from the last run")
    program(root / "node_modules" / ".bin", "tsc", code=2)
    with pytest.raises(cnc.ConsumerError):
        cnc.check()
    assert not leftover.exists()
    assert (cnc.SCRATCH / "tarballs").is_dir()


def test_targets_reads_a_string_through_nested_conditions_and_ignores_anything_else() -> None:
    assert cnc.targets("./a.js") == {"./a.js"}
    assert cnc.targets({"import": {"types": "./a.d.ts", "default": "./a.js"}}) == {
        "./a.d.ts",
        "./a.js",
    }
    assert cnc.targets(None) == set()
    assert cnc.targets(["./a.js"]) == set()
    assert cnc.targets({"import": 1}) == set()
