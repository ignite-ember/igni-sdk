"""The bundle's pieces on their own: the runner, the sources, the resolver and the wheelhouse.

`test_bundle.py` builds whole bundles; here each piece is called
directly, with real `uv` and `pip` against a local find-links directory
wherever a command is run, so what is pinned is what the piece does.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from collections.abc import Iterable, Sequence
from pathlib import Path

import pytest

from igni_service import BundleError
from igni_service.bundle.platforms import PLATFORMS
from igni_service.bundle.requirements import Requirement
from igni_service.bundle.resolver import Resolver
from igni_service.bundle.runner import CommandRunner
from igni_service.bundle.sources import PackageSources
from igni_service.bundle.wheelhouse import Wheelhouse

from .test_bundle import ScriptedRunner, build_dist, write_extension, write_package
from .test_bundle import index as index  # noqa: F401 — the fixture

MACOS, LINUX, WINDOWS = PLATFORMS


def offline(index: Path) -> PackageSources:
    return PackageSources(find_links=(index,), no_index=True, build_isolation=False)


def printed(command_env: str, **kwargs: object) -> str:
    """What the child prints of one environment variable."""
    done = CommandRunner().run(
        [sys.executable, "-c", f"import os; print(os.environ.get({command_env!r}, '<unset>'))"],
        **kwargs,  # type: ignore[arg-type]
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


class TestTheRunner:
    def test_what_it_builds_is_dated_by_a_fixed_epoch(self) -> None:
        assert printed("SOURCE_DATE_EPOCH") == "315532800"

    def test_the_child_inherits_the_parents_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IGNI_AUDIT_INHERITED", "from the parent")

        assert printed("IGNI_AUDIT_INHERITED") == "from the parent"

    def test_extra_environment_is_added_and_wins_over_what_is_inherited(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IGNI_AUDIT_INHERITED", "from the parent")

        assert printed("IGNI_AUDIT_NEW", extra_env=[("IGNI_AUDIT_NEW", "added")]) == "added"
        assert (
            printed("IGNI_AUDIT_INHERITED", extra_env=[("IGNI_AUDIT_INHERITED", "overridden")])
            == "overridden"
        )

    def test_extra_environment_may_replace_the_epoch(self) -> None:
        assert printed("SOURCE_DATE_EPOCH", extra_env=[("SOURCE_DATE_EPOCH", "7")]) == "7"

    def test_a_command_runs_in_the_directory_it_is_given_and_otherwise_in_this_one(
        self, tmp_path: Path
    ) -> None:
        where = [sys.executable, "-c", "import os; print(os.getcwd())"]

        there = CommandRunner().run(where, cwd=tmp_path)
        here = CommandRunner().run(where)

        assert Path(there.stdout.strip()).resolve() == tmp_path.resolve()
        assert Path(here.stdout.strip()).resolve() == Path.cwd().resolve()

    def test_a_failing_command_is_returned_with_its_output_as_text_not_raised(self) -> None:
        done = CommandRunner().run(
            [
                sys.executable,
                "-c",
                "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)",
            ]
        )

        assert (done.returncode, done.stdout.strip(), done.stderr.strip()) == (3, "out", "err")

    def test_arguments_reach_the_command_as_they_are_with_no_shell_in_between(self) -> None:
        awkward = "a b; echo $HOME 'quoted' *"

        done = CommandRunner().run(
            [sys.executable, "-c", "import sys; print(sys.argv[1])", awkward]
        )

        assert done.stdout.strip() == awkward

    def test_a_command_that_is_not_there_is_not_run(self) -> None:
        with pytest.raises(FileNotFoundError):
            CommandRunner().run(["igni-audit-no-such-command"])

    def test_output_that_is_not_utf8_is_read_with_replacement_characters(self) -> None:
        done = CommandRunner().run(
            [sys.executable, "-c", "import sys; sys.stderr.buffer.write(b'bad \\xff byte')"]
        )

        assert done.stderr == "bad � byte"


class TestTheSources:
    def test_by_default_nothing_is_said_to_uv_or_pip(self) -> None:
        sources = PackageSources()

        assert sources.index_flags() == []
        assert sources.uv_isolation_flags() == []
        assert sources.pip_isolation_flags() == []

    def test_no_index_alone_is_one_flag(self) -> None:
        assert PackageSources(no_index=True).index_flags() == ["--no-index"]

    def test_find_links_follow_no_index_each_in_its_order(self) -> None:
        sources = PackageSources(
            find_links=("b dir", "a", "/nowhere/at all"),  # type: ignore[arg-type]
            no_index=True,
        )

        assert sources.index_flags() == [
            "--no-index",
            "--find-links",
            "b dir",
            "--find-links",
            "a",
            "--find-links",
            "/nowhere/at all",
        ]

    def test_find_links_without_no_index_leave_the_index_in_use(self) -> None:
        sources = PackageSources(find_links=(Path("wheels"),))

        assert sources.index_flags() == ["--find-links", "wheels"]

    def test_without_isolation_uv_builds_with_this_interpreter_and_pip_without_isolation(
        self,
    ) -> None:
        sources = PackageSources(build_isolation=False)

        assert sources.uv_isolation_flags() == ["--no-build-isolation", "--python", sys.executable]
        assert sources.pip_isolation_flags() == ["--no-build-isolation"]

    def test_strings_are_paths_and_the_sources_cannot_be_changed(self) -> None:
        sources = PackageSources(find_links=("wheels",))  # type: ignore[arg-type]

        assert sources.find_links == (Path("wheels"),)
        with pytest.raises(ValueError, match="frozen"):
            sources.no_index = True


class StderrRunner(ScriptedRunner):
    """Fails every command with one stderr, and keeps what it was run with."""

    def __init__(self, stderr: str) -> None:
        super().__init__(returncode=2, stderr=stderr)
        self.environments: list[tuple[tuple[str, str], ...]] = []

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        extra_env: Iterable[tuple[str, str]] = (),
    ) -> subprocess.CompletedProcess[str]:
        self.environments.append(tuple(extra_env))
        return super().run(command, cwd=cwd)


def failure_of(stderr: str, tmp_path: Path) -> str:
    runner = StderrRunner(stderr)
    resolver = Resolver(tmp_path, PackageSources(), runner)
    with pytest.raises(BundleError) as failed:
        resolver.requirements(WINDOWS, tmp_path)
    return str(failed.value)


class TestTheResolverSaysWhereElseToGetTheSdks:
    @pytest.mark.parametrize(
        "stderr",
        [
            "  x No solution found: igni-extension was not found in the package registry",
            "igni-service not found",
            "Because there are no versions of igni-extension>=9 and the project depends on it",
            "igni-service has no versions that satisfy it",
        ],
    )
    def test_each_way_uv_says_an_sdk_is_missing_carries_the_hint(
        self, stderr: str, tmp_path: Path
    ) -> None:
        said = failure_of(stderr, tmp_path)

        assert said.startswith("could not resolve the dependencies for Windows x86_64:\n")
        assert stderr in said
        assert said.endswith(Resolver.WHEELS_HINT)

    @pytest.mark.parametrize(
        "stderr",
        [
            "  x No solution found: leftpad was not found in the package registry",
            "igni-extension is fine\nbut somepackage was not found",
            "igni-extension\nwas not found",
            "an unrelated failure",
        ],
    )
    def test_any_other_failure_is_said_as_uv_said_it_with_no_hint(
        self, stderr: str, tmp_path: Path
    ) -> None:
        said = failure_of(stderr, tmp_path)

        assert said == f"could not resolve the dependencies for Windows x86_64:\n{stderr}"

    def test_the_hint_names_the_release_the_flag_and_a_checkout_build(self) -> None:
        hint = Resolver.WHEELS_HINT

        assert hint.startswith("igni-extension and igni-service are on PyPI.")
        assert "gh release download sdk-v<version> --repo ignite-ember/igni-sdk" in hint
        assert "--find-links ./sdk-wheels" in hint
        assert "uv build --wheel --out-dir ./sdk-wheels <igni-sdk checkout>/" in hint
        assert Resolver.SDKS == ("igni-extension", "igni-service")

    def test_a_platform_s_own_environment_reaches_uv(self, tmp_path: Path) -> None:
        runner = StderrRunner("x")
        resolver = Resolver(tmp_path, PackageSources(), runner)
        for platform in PLATFORMS:
            with pytest.raises(BundleError):
                resolver.requirements(platform, tmp_path)

        assert runner.environments == [platform.uv_env for platform in PLATFORMS]
        assert runner.environments[0] == (("MACOSX_DEPLOYMENT_TARGET", "26.0"),)


class TestTheResolverPinsForTheTargetNotTheMachine:
    def pin(self, extension: Path, index: Path, platform: object, scratch: Path) -> list[str]:
        resolver = Resolver(extension, offline(index), CommandRunner())
        return resolver.requirements(platform, scratch)  # type: ignore[arg-type]

    def test_a_marker_is_judged_for_the_platform_asked(self, tmp_path: Path, index: Path) -> None:
        extension = write_extension(
            tmp_path / "extension", dependencies=["tinydep; sys_platform == 'win32'"]
        )

        names = {
            platform.name: [
                Requirement.name_of(r) for r in self.pin(extension, index, platform, tmp_path)
            ]
            for platform in PLATFORMS
        }

        assert names == {MACOS.name: [], LINUX.name: [], WINDOWS.name: ["tinydep"]}

    def test_every_pin_is_one_line_with_its_hashes(self, tmp_path: Path, index: Path) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=["tinydep"])

        [pinned] = self.pin(extension, index, LINUX, tmp_path)

        assert pinned.startswith("tinydep==1.0.0 --hash=sha256:")
        assert "\n" not in pinned and "\\" not in pinned

    def test_an_extension_with_no_dependencies_pins_nothing(
        self, tmp_path: Path, index: Path
    ) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=[])

        assert self.pin(extension, index, MACOS, tmp_path) == []

    def test_the_pins_are_written_to_a_file_named_for_the_platform(
        self, tmp_path: Path, index: Path
    ) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=["tinydep"])

        self.pin(extension, index, WINDOWS, tmp_path)

        assert (tmp_path / "requirements-x86_64-pc-windows-msvc.txt").is_file()

    def test_a_path_source_in_the_extension_s_pyproject_is_not_followed(
        self, tmp_path: Path, index: Path
    ) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=["tinydep"])
        pyproject = extension / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text()
            + textwrap.dedent(
                f"""
                [tool.uv.sources]
                tinydep = {{ path = "{tmp_path / "tinydep"}" }}
                """
            )
        )

        [pinned] = self.pin(extension, index, LINUX, tmp_path)

        assert "file://" not in pinned and "@" not in pinned
        assert pinned.startswith("tinydep==1.0.0 --hash=sha256:")

    def test_a_dependency_nothing_offers_stops_the_resolution_with_no_hint(
        self, tmp_path: Path, index: Path
    ) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=["leftpad-nowhere"])

        with pytest.raises(BundleError) as failed:
            self.pin(extension, index, MACOS, tmp_path)

        said = str(failed.value)
        assert said.startswith("could not resolve the dependencies for macOS arm64:\n")
        assert "leftpad-nowhere" in said
        assert Resolver.WHEELS_HINT not in said


class ExtraWheelRunner(CommandRunner):
    """Runs for real, but first leaves wheels in the build's out directory."""

    def __init__(self, leave: Sequence[str]) -> None:
        self.leave = leave

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        extra_env: Iterable[tuple[str, str]] = (),
    ) -> subprocess.CompletedProcess[str]:
        out = Path(command[command.index("--out-dir") + 1])
        out.mkdir(parents=True, exist_ok=True)
        for name in self.leave:
            (out / name).write_bytes(b"")
        return subprocess.CompletedProcess[str](list(command), 0, "", "")


def wheelhouse(
    extension: Path,
    index: Path,
    *,
    platforms: Sequence[object] = PLATFORMS,
    allow_sdist: set[str] | None = None,
    runner: CommandRunner | None = None,
) -> Wheelhouse:
    return Wheelhouse(
        extension,
        sources=offline(index),
        runner=runner or CommandRunner(),
        platforms=platforms,  # type: ignore[arg-type]
        allow_sdist=allow_sdist or set(),
    )


class TestTheExtensionsOwnWheel:
    def test_it_is_built_and_copied_into_the_wheelhouse(self, tmp_path: Path, index: Path) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=[])
        into = tmp_path / "wheels"
        into.mkdir()

        wheel = wheelhouse(extension, index).add_extension("acme-example", into, tmp_path / "s")

        assert wheel == into / "acme_example-1.0.0-py3-none-any.whl"
        assert wheel.is_file()

    def test_the_package_is_named_by_its_pep_503_name(self, tmp_path: Path, index: Path) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=[])
        into = tmp_path / "wheels"
        into.mkdir()

        wheel = wheelhouse(extension, index).add_extension("Acme.Example", into, tmp_path / "s")

        assert wheel.name == "acme_example-1.0.0-py3-none-any.whl"

    def test_a_wheel_of_another_package_is_refused(self, tmp_path: Path, index: Path) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=[])
        into = tmp_path / "wheels"
        into.mkdir()

        with pytest.raises(BundleError) as failed:
            wheelhouse(extension, index).add_extension("other-package", into, tmp_path / "s")

        assert str(failed.value) == (
            "the extension built acme_example-1.0.0-py3-none-any.whl, not other-package"
        )
        assert list(into.iterdir()) == []

    def test_a_build_that_fails_says_what_uv_said(self, tmp_path: Path, index: Path) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=[])
        (extension / "pyproject.toml").write_text("[project\nbroken")
        into = tmp_path / "wheels"
        into.mkdir()

        with pytest.raises(BundleError) as failed:
            wheelhouse(extension, index).add_extension("acme-example", into, tmp_path / "s")

        assert str(failed.value).startswith("could not build the extension's wheel:\n")
        assert "pyproject.toml" in str(failed.value)

    @pytest.mark.parametrize(
        ("left", "said"),
        [
            ([], "expected one extension wheel, found []"),
            (
                ["b-1.0-py3-none-any.whl", "a-1.0-py3-none-any.whl"],
                "expected one extension wheel, found "
                "['a-1.0-py3-none-any.whl', 'b-1.0-py3-none-any.whl']",
            ),
        ],
    )
    def test_a_build_that_leaves_no_wheel_or_two_is_refused(
        self, left: list[str], said: str, tmp_path: Path, index: Path
    ) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=[])
        into = tmp_path / "wheels"
        into.mkdir()
        house = wheelhouse(extension, index, runner=ExtraWheelRunner(left))

        with pytest.raises(BundleError) as failed:
            house.add_extension("acme-example", into, tmp_path / "s")

        assert str(failed.value) == said
        assert list(into.iterdir()) == []


class TestFillingTheWheelhouse:
    def test_every_platform_s_wheels_are_taken_and_nothing_is_said(
        self, tmp_path: Path, index: Path
    ) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=["tinydep"])
        into = tmp_path / "wheels"
        into.mkdir()

        notes = wheelhouse(extension, index).fill(into, tmp_path)

        assert notes == []
        assert [path.name for path in into.iterdir()] == ["tinydep-1.0.0-py3-none-any.whl"]

    def test_all_the_platforms_built_need_no_note(self, tmp_path: Path, index: Path) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=[])

        assert wheelhouse(extension, index).platform_notes() == []
        assert (
            wheelhouse(extension, index, platforms=tuple(reversed(PLATFORMS))).platform_notes()
            == []
        )

    def test_some_platforms_only_are_named_and_the_others_said_unable(
        self, tmp_path: Path, index: Path
    ) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=[])

        notes = wheelhouse(extension, index, platforms=[LINUX, MACOS]).platform_notes()

        assert notes == [
            "wheels for Linux x86_64, macOS arm64 only: "
            "a machine on any other platform cannot install this bundle"
        ]

    def test_several_requirements_with_no_wheel_are_listed_in_order_by_every_platform(
        self, tmp_path: Path, index: Path
    ) -> None:
        build_dist(
            write_package(tmp_path / "another", "another-sdist", dependencies=[]), index, "--sdist"
        )
        extension = write_extension(
            tmp_path / "extension", dependencies=["sdistonly", "another-sdist"]
        )
        into = tmp_path / "wheels"
        into.mkdir()

        with pytest.raises(BundleError) as failed:
            wheelhouse(extension, index).fill(into, tmp_path)

        said = str(failed.value)
        assert said.startswith("dependencies with no usable wheel:\n")
        assert said.index("another-sdist==1.0.0") < said.index("sdistonly==1.0.0")
        for requirement in ("another-sdist==1.0.0", "sdistonly==1.0.0"):
            [line] = [part for part in said.splitlines() if part.strip().startswith(requirement)]
            assert line.endswith(
                "no cp312/abi3/pure wheel for macOS arm64, Linux x86_64, Windows x86_64"
            )
        assert "[tool.igni.bundle] sdist-only" in said

    def test_the_allowed_names_are_compared_as_pep_503_names(
        self, tmp_path: Path, index: Path
    ) -> None:
        build_dist(
            write_package(tmp_path / "dotted", "Dotted_Sdist", dependencies=[]), index, "--sdist"
        )
        extension = write_extension(tmp_path / "extension", dependencies=["dotted.sdist"])
        into = tmp_path / "wheels"
        into.mkdir()

        notes = wheelhouse(extension, index, allow_sdist={"dotted-sdist"}).fill(into, tmp_path)

        [note] = notes
        assert note.startswith("dotted-sdist==1.0.0: no wheel for macOS arm64, Linux x86_64, ")
        assert "built dotted_sdist-1.0.0-py3-none-any.whl from its sdist" in note

    def test_a_requirement_not_allowed_stops_the_build_even_when_another_is(
        self, tmp_path: Path, index: Path
    ) -> None:
        build_dist(
            write_package(tmp_path / "another", "another-sdist", dependencies=[]), index, "--sdist"
        )
        extension = write_extension(
            tmp_path / "extension", dependencies=["sdistonly", "another-sdist"]
        )
        into = tmp_path / "wheels"
        into.mkdir()

        with pytest.raises(BundleError) as failed:
            wheelhouse(extension, index, allow_sdist={"sdistonly"}).fill(into, tmp_path)

        said = str(failed.value)
        assert "another-sdist==1.0.0" in said
        assert "sdistonly==1.0.0" not in said

    def test_a_resolution_that_fails_on_a_platform_stops_the_fill(
        self, tmp_path: Path, index: Path
    ) -> None:
        extension = write_extension(
            tmp_path / "extension", dependencies=["leftpad-nowhere; sys_platform == 'win32'"]
        )
        into = tmp_path / "wheels"
        into.mkdir()

        with pytest.raises(BundleError, match="could not resolve the dependencies for Windows"):
            wheelhouse(extension, index).fill(into, tmp_path)

    def test_no_platforms_fill_nothing_and_say_so(self, tmp_path: Path, index: Path) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=["tinydep"])
        into = tmp_path / "wheels"
        into.mkdir()
        house = wheelhouse(extension, index, platforms=[])

        assert house.fill(into, tmp_path) == []
        assert list(into.iterdir()) == []
        assert os.fspath(into)  # the directory is still there
