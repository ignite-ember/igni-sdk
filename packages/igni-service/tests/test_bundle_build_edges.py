"""The bundle builder, command, downloader and code reader, at their edges.

`test_bundle.py` and `test_assets.py` build real bundles from a local
index. This holds the rest of what a user sees to the code: what is
staged and what is not, the printed lines, the exit codes, what pip is
asked and what is said when it answers badly, and what a real `uv run`
reads from a wheelhouse.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tarfile
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

import httpx
import pytest

from igni_service import BundleError
from igni_service.assets import AssetFetcher, AssetPlatform, BundleLayout
from igni_service.bundle.builder import BundleBuilder
from igni_service.bundle.code_tools import CodeTools, CodeToolsRead
from igni_service.bundle.command import BundleCommand, main
from igni_service.bundle.downloads import PipDownloader
from igni_service.bundle.platforms import PLATFORMS
from igni_service.bundle.runner import CommandRunner
from igni_service.bundle.sources import PackageSources

from .test_assets import JRE, MODEL, declared, every_asset, with_assets
from .test_bundle import (
    LOOKUP,
    StubTools,
    build_dist,
    builder,
    members,
    write_extension,
    write_package,
)
from .test_bundle import (
    index as index,  # noqa: F401 — the fixture
)

Answer = subprocess.CompletedProcess[str]


def answered(returncode: int = 0, stdout: str = "", stderr: str = "") -> Answer:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class QueueRunner(CommandRunner):
    """Answers each command with the next script entry, and keeps what it was asked."""

    def __init__(self, *script: Answer | Callable[[list[str]], Answer]) -> None:
        self.script = list(script)
        self.commands: list[list[str]] = []

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        extra_env: Iterable[tuple[str, str]] = (),
    ) -> Answer:
        self.commands.append(list(command))
        step = self.script.pop(0) if self.script else answered()
        return step(list(command)) if callable(step) else step


def wants_of(command: list[str]) -> list[str]:
    """The requirement lines the command's `-r` file holds at the moment it runs."""
    return Path(command[command.index("-r") + 1]).read_text().splitlines()


def no_match(requirement: str) -> Answer:
    return answered(1, stderr=f"ERROR: No matching distribution found for {requirement}\n")


def asking(seen: list[list[str]], answer: Answer | None = None) -> Callable[[list[str]], Answer]:
    """A step that notes the requirements it was asked for, then answers."""

    def step(command: list[str]) -> Answer:
        seen.append(wants_of(command))
        return answer or answered()

    return step


LINUX = PLATFORMS[1]


class TestWhatPipIsAsked:
    @staticmethod
    def downloader(runner: CommandRunner, find_links: tuple[Path, ...] = ()) -> PipDownloader:
        return PipDownloader(["pip"], PackageSources(find_links=find_links, no_index=True), runner)

    @staticmethod
    def into(tmp_path: Path) -> Path:
        into = tmp_path / "wheels"
        into.mkdir()
        return into

    def test_the_download_is_for_cpython_312_wheels_only_with_hashes_required(
        self, tmp_path: Path
    ) -> None:
        runner = QueueRunner(lambda command: answered())
        into = self.into(tmp_path)

        assert self.downloader(runner).download(["a==1 --hash=sha256:aa"], LINUX, into) == []

        [command] = runner.commands
        assert command[:2] == ["pip", "download"]
        for flag in ("--require-hashes", "--only-binary=:all:", "--no-deps", "--no-index"):
            assert flag in command
        assert command[command.index("--python-version") + 1] == "3.12"
        assert command[command.index("--implementation") + 1] == "cp"
        abis = [command[i + 1] for i, part in enumerate(command) if part == "--abi"]
        assert abis == ["cp312", "abi3", "none"]
        platforms = [command[i + 1] for i, part in enumerate(command) if part == "--platform"]
        assert platforms == list(LINUX.pip)
        assert command[command.index("--dest") + 1] == str(into)

    def test_one_run_asks_for_the_lot_and_leaves_no_list_behind(self, tmp_path: Path) -> None:
        seen: list[list[str]] = []
        runner = QueueRunner(asking(seen))
        into = self.into(tmp_path)

        self.downloader(runner).download(
            ["a==1 --hash=sha256:aa", "b==2 --hash=sha256:bb"], LINUX, into
        )

        assert seen == [["a==1 --hash=sha256:aa", "b==2 --hash=sha256:bb"]]
        assert list(tmp_path.glob("want-*.txt")) == []

    def test_nothing_to_download_runs_nothing(self, tmp_path: Path) -> None:
        runner = QueueRunner()

        assert self.downloader(runner).download([], LINUX, self.into(tmp_path)) == []

        assert runner.commands == []

    def test_each_requirement_pip_names_is_set_aside_and_the_rest_asked_again(
        self, tmp_path: Path
    ) -> None:
        seen: list[list[str]] = []

        def refuse(name: str) -> Callable[[list[str]], Answer]:
            return asking(seen, no_match(name))

        runner = QueueRunner(
            refuse("a==1"),
            refuse("b==2"),
            asking(seen),
        )
        requirements = [
            f"{n}=={v} --hash=sha256:{n * 2}" for n, v in (("a", 1), ("b", 2), ("c", 3))
        ]

        missing = self.downloader(runner).download(requirements, LINUX, self.into(tmp_path))

        assert missing == [requirements[0], requirements[1]]
        assert seen == [requirements, requirements[1:], requirements[2:]]

    def test_when_every_requirement_is_refused_all_are_answered_back(self, tmp_path: Path) -> None:
        runner = QueueRunner(no_match("a==1"), no_match("b==2"))
        requirements = ["a==1 --hash=sha256:aa", "b==2 --hash=sha256:bb"]

        missing = self.downloader(runner).download(requirements, LINUX, self.into(tmp_path))

        assert missing == requirements
        assert len(runner.commands) == 2

    def test_a_name_in_another_spelling_still_finds_its_requirement(self, tmp_path: Path) -> None:
        runner = QueueRunner(no_match("Some_Pkg==1"))
        requirement = "some-pkg==1 --hash=sha256:aa"

        missing = self.downloader(runner).download([requirement], LINUX, self.into(tmp_path))

        assert missing == [requirement]

    def test_any_other_failure_stops_the_build_naming_the_platform_and_what_pip_said(
        self, tmp_path: Path
    ) -> None:
        runner = QueueRunner(answered(1, stderr="ERROR: HTTP error 500\n"))

        with pytest.raises(BundleError) as failed:
            self.downloader(runner).download(["a==1 --hash=sha256:aa"], LINUX, self.into(tmp_path))

        assert str(failed.value) == "pip download failed for Linux x86_64:\nERROR: HTTP error 500\n"

    def test_a_distribution_pip_names_that_was_not_asked_for_is_a_failure_not_a_loop(
        self, tmp_path: Path
    ) -> None:
        runner = QueueRunner(no_match("stranger==9"))

        with pytest.raises(BundleError, match="pip download failed for Linux x86_64"):
            self.downloader(runner).download(["a==1 --hash=sha256:aa"], LINUX, self.into(tmp_path))
        assert len(runner.commands) == 1

    def test_a_local_wheel_is_taken_and_only_the_rest_is_asked_of_pip(self, tmp_path: Path) -> None:
        links = tmp_path / "links"
        links.mkdir()
        body = b"pinned wheel bytes"
        (links / "a-1-py3-none-any.whl").write_bytes(body)
        seen: list[list[str]] = []
        runner = QueueRunner(asking(seen))
        taken = f"a==1 --hash=sha256:{hashlib.sha256(body).hexdigest()}"
        other = "b==2 --hash=sha256:" + "0" * 64
        into = self.into(tmp_path)

        self.downloader(runner, (links,)).download([taken, other], LINUX, into)

        assert seen == [[other]]
        assert [p.name for p in into.iterdir()] == ["a-1-py3-none-any.whl"]

    def test_a_wheel_over_one_mebibyte_is_digested_whole(self, tmp_path: Path) -> None:
        links = tmp_path / "links"
        links.mkdir()
        body = bytes(range(256)) * (10 * 1024) + b"tail"
        assert len(body) > 2 * (1 << 20)
        (links / "big-1-py3-none-any.whl").write_bytes(body)
        runner = QueueRunner()
        into = self.into(tmp_path)

        self.downloader(runner, (links,)).download(
            [f"big==1 --hash=sha256:{hashlib.sha256(body).hexdigest()}"], LINUX, into
        )

        assert runner.commands == []
        assert (into / "big-1-py3-none-any.whl").read_bytes() == body

    def test_two_local_wheels_with_the_same_bytes_give_the_first_by_name(
        self, tmp_path: Path
    ) -> None:
        links = tmp_path / "links"
        links.mkdir()
        for name in ("b-1-py3-none-any.whl", "a-1-py3-none-any.whl"):
            (links / name).write_bytes(b"same")
        into = self.into(tmp_path)

        self.downloader(QueueRunner(), (links,)).download(
            [f"a==1 --hash=sha256:{hashlib.sha256(b'same').hexdigest()}"], LINUX, into
        )

        assert [p.name for p in into.iterdir()] == ["a-1-py3-none-any.whl"]

    def test_pip_is_this_interpreters_when_it_answers_and_uvx_s_when_it_does_not(
        self, tmp_path: Path
    ) -> None:
        own = QueueRunner(answered(0))
        PipDownloader.find(PackageSources(), own).download(
            ["a==1 --hash=sha256:aa"], LINUX, self.into(tmp_path)
        )
        assert own.commands[0] == [sys.executable, "-m", "pip", "--version"]
        assert own.commands[1][:4] == [sys.executable, "-m", "pip", "download"]

        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        uvx = QueueRunner(answered(1))
        PipDownloader.find(PackageSources(), uvx).download(
            ["a==1 --hash=sha256:aa"], LINUX, self.into(elsewhere)
        )
        assert uvx.commands[1][:5] == ["uvx", "--from", "pip", "pip", "download"]


class TestBuildingAWheelFromAnSdist:
    REQUIREMENT = "sdistonly==1.0.0 --hash=sha256:" + "a" * 64

    @staticmethod
    def downloader(runner: CommandRunner) -> PipDownloader:
        return PipDownloader(["pip"], PackageSources(build_isolation=False), runner)

    @staticmethod
    def makes(*wheels: str) -> Callable[[list[str]], Answer]:
        def run(command: list[str]) -> Answer:
            built = Path(command[command.index("-w") + 1])
            for wheel in wheels:
                (built / wheel).write_bytes(b"wheel " + wheel.encode())
            return answered()

        return run

    @pytest.fixture
    def places(self, tmp_path: Path) -> tuple[Path, Path]:
        into, scratch = tmp_path / "into", tmp_path / "scratch"
        into.mkdir()
        scratch.mkdir()
        return into, scratch

    def test_a_pure_wheel_is_built_from_the_hashed_sdist_and_copied(
        self, places: tuple[Path, Path]
    ) -> None:
        into, scratch = places
        seen: list[list[str]] = []

        def run(command: list[str]) -> Answer:
            seen.append(wants_of(command))
            return self.makes("sdistonly-1.0.0-py3-none-any.whl")(command)

        runner = QueueRunner(run)

        wheel = self.downloader(runner).wheel_from_sdist(self.REQUIREMENT, into, scratch)

        assert wheel == into / "sdistonly-1.0.0-py3-none-any.whl"
        assert wheel.read_bytes() == b"wheel sdistonly-1.0.0-py3-none-any.whl"
        assert seen == [[self.REQUIREMENT]]
        [command] = runner.commands
        assert command[:2] == ["pip", "wheel"]
        for flag in ("--no-deps", "--require-hashes", "--no-build-isolation"):
            assert flag in command
        assert command[command.index("--no-binary") + 1] == ":all:"

    def test_a_wheel_that_is_not_pure_python_is_refused_by_name(
        self, places: tuple[Path, Path]
    ) -> None:
        into, scratch = places
        runner = QueueRunner(self.makes("sdistonly-1.0.0-cp312-cp312-linux_x86_64.whl"))

        with pytest.raises(BundleError) as refused:
            self.downloader(runner).wheel_from_sdist(self.REQUIREMENT, into, scratch)

        assert "built sdistonly-1.0.0-cp312-cp312-linux_x86_64.whl from its sdist" in str(
            refused.value
        )
        assert "not pure Python" in str(refused.value)
        assert list(into.iterdir()) == []

    def test_a_build_that_yields_another_distribution_produced_no_wheel(
        self, places: tuple[Path, Path]
    ) -> None:
        into, scratch = places
        runner = QueueRunner(self.makes("somethingelse-1.0.0-py3-none-any.whl"))

        with pytest.raises(BundleError) as refused:
            self.downloader(runner).wheel_from_sdist(self.REQUIREMENT, into, scratch)

        assert str(refused.value) == f"{self.REQUIREMENT}: building its sdist produced no wheel"
        assert list(into.iterdir()) == []

    def test_a_build_that_fails_says_what_pip_said(self, places: tuple[Path, Path]) -> None:
        into, scratch = places
        runner = QueueRunner(answered(1, stderr="error: build backend blew up\n"))

        with pytest.raises(BundleError) as refused:
            self.downloader(runner).wheel_from_sdist(self.REQUIREMENT, into, scratch)

        assert str(refused.value) == (
            f"{self.REQUIREMENT}: could not build a wheel from its sdist:\n"
            "error: build backend blew up\n"
        )


class TestReadingToolsFromTheWheelhouse:
    @staticmethod
    def wheelhouse(tmp_path: Path) -> Path:
        (tmp_path / "igni_extension-0.1.0-py3-none-any.whl").write_bytes(b"")
        return tmp_path

    @staticmethod
    def said(
        tmp_path: Path, *, returncode: int = 0, stdout: str = "", stderr: str = ""
    ) -> CodeToolsRead:
        wheels = TestReadingToolsFromTheWheelhouse.wheelhouse(tmp_path)
        runner = QueueRunner(answered(returncode, stdout, stderr))
        return CodeTools(runner).read(wheels, "acme-example", "acme_example")

    def test_the_command_is_uv_run_offline_in_a_throwaway_environment_from_the_wheelhouse(
        self, tmp_path: Path
    ) -> None:
        wheels = self.wheelhouse(tmp_path)
        runner = QueueRunner(answered(stdout='{"tools": []}'))

        read = CodeTools(runner).read(wheels, "acme-example", "acme_example")

        assert read == CodeToolsRead(tools=[])
        assert runner.commands == [
            [
                "uv", "run", "--no-project", "--isolated", "--offline", "--no-index",
                "--find-links", str(wheels), "--python", sys.executable,
                "--with", "acme-example",
                "python", "-m", "igni_extension.manifest", "acme_example",
            ]
        ]  # fmt: skip

    def test_an_empty_wheelhouse_runs_nothing(self, tmp_path: Path) -> None:
        runner = QueueRunner()

        assert CodeTools(runner).read(tmp_path, "a", "a") == CodeToolsRead()
        assert runner.commands == []

    def test_stderr_with_only_blanks_says_no_output(self, tmp_path: Path) -> None:
        assert self.said(tmp_path, returncode=1, stderr="  \n\t\n").problem == "no output"

    def test_a_line_that_starts_with_error_is_chosen_over_the_last_line(
        self, tmp_path: Path
    ) -> None:
        said = self.said(tmp_path, returncode=2, stderr="note\nerror: no such wheel\nhint: try\n")

        assert said.problem == "error: no such wheel"

    def test_a_line_from_igni_extension_is_chosen_and_the_cross_is_trimmed(
        self, tmp_path: Path
    ) -> None:
        said = self.said(
            tmp_path, returncode=1, stderr="igni_extension.manifest: no such module\nlater\n"
        )

        assert said.problem == "igni_extension.manifest: no such module"

    @pytest.mark.parametrize(
        "stdout",
        [
            "",
            "[]",
            '{"id": "x"}',
            '{"tools": "none"}',
            '{"tools": [{"name": "t"}]}',
            '{"tools": [{"name": "t", "annotations": {"readOnlyHint": true}}]}',
            json.dumps({"tools": [{**LOOKUP, "surprise": 1}]}),
        ],
    )
    def test_an_answer_that_is_not_the_listing_is_a_problem_not_a_crash(
        self, tmp_path: Path, stdout: str
    ) -> None:
        read = self.said(tmp_path, stdout=stdout)

        assert read.tools is None
        assert read.problem.startswith("igni_extension.manifest answered something else")

    def test_a_real_uv_run_reads_the_listing_from_the_wheelhouse_alone(
        self, tmp_path: Path
    ) -> None:
        """The command as uv runs it: offline, from the wheelhouse, in a fresh environment."""
        wheels = tmp_path / "wheels"
        listing = json.dumps({"tools": [LOOKUP]})
        sdk = write_package(tmp_path / "sdk", "igni-extension", dependencies=[])
        (sdk / "src" / "igni_extension" / "manifest.py").write_text(
            "import sys\n"
            f"if __name__ == '__main__':\n    print({listing!r}, file=sys.stdout)\n"
            "    sys.stderr.write('read ' + sys.argv[1])\n"
        )
        write_package(tmp_path / "acme", "acme-example", dependencies=["igni-extension"])
        build_dist(sdk, wheels, "--wheel")
        build_dist(tmp_path / "acme", wheels, "--wheel")

        class Clean(CommandRunner):
            def run(self, command: Sequence[str], **kwargs: object) -> Answer:
                return super().run(command, extra_env=[("PYTHONPATH", "")])

        read = CodeTools(Clean()).read(wheels, "acme-example", "acme_example")

        assert read.problem == ""
        assert read.tools is not None and [t.name for t in read.tools] == ["acme.example.lookup"]


class TestWhatTheBuilderStagesAndLeaves:
    def test_caches_and_finder_droppings_never_travel_and_sources_do(
        self, tmp_path: Path, index: Path
    ) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=[])
        (extension / "plugin" / "__pycache__").mkdir()
        (extension / "plugin" / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"")
        (extension / "plugin" / "agents" / "stale.pyc").write_bytes(b"")
        (extension / "plugin" / "agents" / ".DS_Store").write_bytes(b"")
        (extension / "ui" / ".DS_Store").write_bytes(b"")
        (extension / "ui" / "app.js").write_text("1")

        report = builder(extension, index).build(tmp_path / "b.tar.gz")

        assert members(report.out) == [
            "README.md",
            "manifest.json",
            "plugin/agents/helper.md",
            "ui/app.js",
            "ui/index.html",
            "wheels/acme_example-1.0.0-py3-none-any.whl",
        ]

    def test_a_readme_plugin_or_ui_that_is_not_there_is_just_left_out(
        self, tmp_path: Path, index: Path
    ) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=[])
        (extension / "README.md").unlink()
        for path in sorted((extension / "plugin").rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        (extension / "plugin").rmdir()
        (extension / "ui" / "index.html").unlink()
        (extension / "ui").rmdir()

        report = builder(extension, index).build(tmp_path / "b.tar.gz")

        assert members(report.out) == [
            "manifest.json",
            "wheels/acme_example-1.0.0-py3-none-any.whl",
        ]

    def test_the_report_says_what_is_on_disk(self, tmp_path: Path, index: Path) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=["tinydep"])
        out = tmp_path / "out" / "deeper" / "bundle.tar.gz"

        report = builder(extension, index).build(out)

        data = out.read_bytes()
        assert report.out == out
        assert (report.size, report.sha256) == (len(data), hashlib.sha256(data).hexdigest())
        assert report.wheels == [
            "acme_example-1.0.0-py3-none-any.whl",
            "tinydep-1.0.0-py3-none-any.whl",
        ]
        assert report.assets_dir == tmp_path / "out" / "deeper" / "bundle.tar.gz".replace(
            ".tar.gz", ".assets"
        )

    def test_an_entry_that_runs_no_module_reads_no_tools(self, tmp_path: Path, index: Path) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=[])
        pyproject = extension / "pyproject.toml"
        pyproject.write_text(pyproject.read_text().replace('"acme_example:main"', '":main"'))

        class Never(CodeTools):
            def read(self, wheels: Path, package: str, module: str) -> CodeToolsRead:
                raise AssertionError("the code was read")

        report = BundleBuilder(
            extension, find_links=[index], no_index=True, build_isolation=False, code_tools=Never()
        ).build(tmp_path / "b.tar.gz")

        assert report.notes == []

    def test_the_scratch_directory_is_gone_after_a_failed_build(
        self, tmp_path: Path, index: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        monkeypatch.setattr("tempfile.tempdir", str(scratch))
        extension = write_extension(tmp_path / "extension", dependencies=["sdistonly"])

        with pytest.raises(BundleError):
            builder(extension, index).build(tmp_path / "b.tar.gz")

        assert list(scratch.iterdir()) == []

    def test_a_missing_pyproject_or_manifest_is_refused_in_words(self, tmp_path: Path) -> None:
        with pytest.raises(BundleError, match="pyproject.toml does not exist"):
            BundleBuilder(tmp_path)

        extension = write_extension(tmp_path / "extension", dependencies=[])
        (extension / "manifest.json").unlink()
        with pytest.raises(BundleError, match="manifest.json does not exist"):
            BundleBuilder(extension).build(tmp_path / "b.tar.gz")
        with pytest.raises(BundleError, match="manifest.json does not exist"):
            BundleBuilder(extension).manifest()

    def test_the_assets_directory_is_made_and_swept_even_when_none_are_declared(
        self, tmp_path: Path, index: Path
    ) -> None:
        extension = write_extension(tmp_path / "extension", dependencies=[])
        out = tmp_path / "b.tar.gz"
        assets = BundleLayout.assets_dir(out)
        assets.mkdir()
        (assets / "left-over").write_bytes(b"old")

        report = builder(extension, index).build(out)

        assert report.assets == []
        assert report.assets_dir == assets and assets.is_dir()
        assert list(assets.iterdir()) == []

    def test_a_declared_asset_the_server_will_not_give_stops_the_build_with_no_archive_kept_as_a_lie(
        self, tmp_path: Path, index: Path
    ) -> None:
        extension = with_assets(
            write_extension(tmp_path / "extension", dependencies=[]),
            [declared("model", AssetPlatform.ANY, MODEL, source="https://downloads.test/nowhere")],
        )
        fetcher = AssetFetcher(transport=httpx.MockTransport(lambda r: httpx.Response(404)))

        with pytest.raises(BundleError, match="answered 404"):
            BundleBuilder(
                extension,
                find_links=[index],
                no_index=True,
                build_isolation=False,
                code_tools=StubTools(),
                fetcher=fetcher,
            ).build(tmp_path / "b.tar.gz")


class TestTheCommandSays:
    @staticmethod
    def run(
        capsys: pytest.CaptureFixture[str], tmp_path: Path, index: Path, *extra: str
    ) -> tuple[int, list[str], str]:
        status = BundleCommand.main(
            [
                "--extension", str(tmp_path / "extension"),
                "--out", str(tmp_path / "b.tar.gz"),
                "--find-links", str(index),
                "--no-index",
                "--no-build-isolation",
                *extra,
            ]
        )  # fmt: skip
        seen = capsys.readouterr()
        return status, seen.out.splitlines(), seen.err

    def test_the_defaults_are_the_extension_directory_and_extension_bundle_tar_gz(self) -> None:
        args = BundleCommand.parser().parse_args([])

        assert args.extension == Path("extension")
        assert args.out == Path("extension-bundle.tar.gz")
        assert (args.allow_sdist, args.find_links, args.platform) == ([], [], [])
        assert (args.no_index, args.no_build_isolation) == (False, False)

    def test_the_options_repeat_and_an_unknown_platform_is_refused(self) -> None:
        args = BundleCommand.parser().parse_args(
            ["--allow-sdist", "a", "--allow-sdist", "b", "--find-links", "x", "--find-links", "y"]
        )
        assert args.allow_sdist == ["a", "b"]
        assert args.find_links == [Path("x"), Path("y")]
        with pytest.raises(SystemExit) as refused:
            BundleCommand.parser().parse_args(["--platform", "plan9"])
        assert refused.value.code == 2

    def test_the_wrote_line_holds_the_path_id_version_wheels_size_and_digest(
        self, tmp_path: Path, index: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_extension(tmp_path / "extension", dependencies=["tinydep"])

        status, out, err = self.run(capsys, tmp_path, index)

        data = (tmp_path / "b.tar.gz").read_bytes()
        assert (status, err) == (0, "")
        assert out == [
            f"extension bundle: wrote {tmp_path / 'b.tar.gz'} — acme.example 1.0.0, "
            f"2 wheels, {len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()}"
        ]

    def test_a_line_for_each_asset_follows_the_wrote_line(
        self, tmp_path: Path, index: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with_assets(
            write_extension(tmp_path / "extension", dependencies=[]),
            every_asset(),
        )
        assets = BundleLayout.assets_dir(tmp_path / "b.tar.gz")
        assets.mkdir()
        for body in [*JRE.values(), MODEL]:
            (assets / hashlib.sha256(body).hexdigest()).write_bytes(body)

        status, out, _ = self.run(capsys, tmp_path, index)

        assert status == 0
        assert out[0].startswith("extension bundle: wrote ")
        assert out[1:] == [
            f"extension bundle: asset jre ({platform}) jre-{platform}.tar.gz, {len(body)} bytes, "
            f"sha256 {hashlib.sha256(body).hexdigest()} in {assets}"
            for platform, body in JRE.items()
        ] + [
            f"extension bundle: asset model (any) model.onnx, {len(MODEL)} bytes, "
            f"sha256 {hashlib.sha256(MODEL).hexdigest()} in {assets}"
        ]

    def test_platforms_restrict_the_wheelhouse_and_the_note_comes_first(
        self, tmp_path: Path, index: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_extension(tmp_path / "extension", dependencies=["tinydep"])

        status, out, _ = self.run(
            capsys, tmp_path, index, "--platform", "windows-x86_64", "--platform", "linux-x86_64"
        )

        assert status == 0
        assert out[0] == (
            "extension bundle: wheels for Linux x86_64, Windows x86_64 only: a machine on "
            "any other platform cannot install this bundle"
        )
        assert out[1].startswith("extension bundle: wrote ")

    def test_no_platform_means_every_platform_and_no_note(
        self, tmp_path: Path, index: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_extension(tmp_path / "extension", dependencies=[])

        _, out, _ = self.run(capsys, tmp_path, index)

        assert len(out) == 1

    def test_a_missing_extension_directory_is_one_line_on_stderr_and_exit_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        status = BundleCommand.main(["--extension", str(tmp_path / "nowhere")])

        seen = capsys.readouterr()
        assert status == 1 and seen.out == ""
        assert seen.err == (
            f"extension bundle: {tmp_path / 'nowhere' / 'pyproject.toml'} does not exist: "
            "the extension is a Python package\n"
        )

    def test_the_console_script_reads_sys_argv_and_returns_the_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["igni-service-bundle", "--extension", str(tmp_path)])

        assert main() == 1
        assert "extension bundle: " in capsys.readouterr().err

    def test_no_index_keeps_every_run_off_the_network(
        self,
        tmp_path: Path,
        index: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An index nobody answers at: only `--no-index` lets the build finish."""
        dead = "http://127.0.0.1:9/simple/"
        for name in ("PIP_INDEX_URL", "UV_INDEX_URL", "UV_DEFAULT_INDEX"):
            monkeypatch.setenv(name, dead)
        monkeypatch.setenv("PIP_RETRIES", "0")
        monkeypatch.setenv("PIP_TIMEOUT", "2")
        monkeypatch.setenv("UV_HTTP_RETRIES", "0")
        write_extension(tmp_path / "extension", dependencies=["tinydep"])

        status, _, err = self.run(capsys, tmp_path, index)

        assert (status, err) == (0, "")

    def test_find_links_and_isolation_reach_the_build(
        self, tmp_path: Path, index: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_extension(tmp_path / "extension", dependencies=["tinydep"])

        status, out, err = self.run(capsys, tmp_path, index)

        assert (status, err) == (0, "")
        assert "2 wheels" in out[0]


class TestRunningItAsAModule:
    @staticmethod
    def run(*argv: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "igni_service.bundle", *argv],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_a_good_build_exits_0_and_prints_the_wrote_line(
        self, tmp_path: Path, index: Path
    ) -> None:
        write_extension(tmp_path / "extension", dependencies=["tinydep"])

        ran = self.run(
            "--extension", str(tmp_path / "extension"),
            "--out", str(tmp_path / "b.tar.gz"),
            "--find-links", str(index),
            "--no-index", "--no-build-isolation",
        )  # fmt: skip

        assert ran.returncode == 0, ran.stderr
        assert ran.stdout.startswith(f"extension bundle: wrote {tmp_path / 'b.tar.gz'}")
        with tarfile.open(fileobj=io.BytesIO((tmp_path / "b.tar.gz").read_bytes())) as tar:
            assert "manifest.json" in tar.getnames()

    def test_a_refused_build_exits_1_with_the_message_on_stderr(self, tmp_path: Path) -> None:
        ran = self.run("--extension", str(tmp_path))

        assert ran.returncode == 1
        assert ran.stdout == ""
        assert ran.stderr.startswith("extension bundle: ")

    def test_bad_arguments_exit_2(self) -> None:
        ran = self.run("--platform", "plan9")

        assert ran.returncode == 2
        assert "invalid choice" in ran.stderr
