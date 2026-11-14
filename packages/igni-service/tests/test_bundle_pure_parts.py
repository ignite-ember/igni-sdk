"""The bundle package's parts that need no uv and no pip: archive, platforms, names and tables.

`test_bundle.py` builds real bundles; this holds each small part to its
contract at its edges: the archive's bytes and what it refuses to read,
the platforms' tags, the requirement parser, the pyproject and manifest
tables, and what `permissions.tools` says when several things differ.
"""

from __future__ import annotations

import gzip
import inspect
import io
import json
import os
import re
import tarfile
import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

import igni_service.bundle as bundle_package
from igni_service import BundleError
from igni_service.bundle.archive import BundleArchive
from igni_service.bundle.code_tools import CodeToolsRead
from igni_service.bundle.manifest import (
    AgentTool,
    BundleManifest,
    PythonPackaging,
    ToolAnnotations,
)
from igni_service.bundle.permissions_tools import PermissionsTools
from igni_service.bundle.platforms import MACOS_TARGET, PLATFORMS, Platform
from igni_service.bundle.project import ExtensionProject
from igni_service.bundle.requirements import HashedRequirements, Requirement

from .test_bundle import EXTENSION, LOOKUP, manifest_of


def tar_of(archive: bytes) -> tarfile.TarFile:
    return tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz")


def gzipped_tar(files: dict[str, bytes], *, types: dict[str, bytes] | None = None) -> bytes:
    """A gzipped tar of `files`, member names as given."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
        for name in types or {}:
            directory = tarfile.TarInfo(name)
            directory.type = tarfile.DIRTYPE
            tar.addfile(directory)
    return gzip.compress(raw.getvalue())


class TestTheArchiveIsDeterministic:
    @staticmethod
    def staged(root: Path, order: list[str]) -> Path:
        for name in order:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(f"body of {name}")
        return root

    def test_files_with_other_times_modes_and_creation_order_give_the_same_bytes(
        self, tmp_path: Path
    ) -> None:
        names = ["manifest.json", "wheels/b.whl", "wheels/a.whl", "ui/index.html"]
        one = self.staged(tmp_path / "one", names)
        two = self.staged(tmp_path / "two", list(reversed(names)))
        for index, path in enumerate(sorted(two.rglob("*"))):
            if path.is_file():
                os.utime(path, (1_000_000 + index, 2_000_000 + index))
                path.chmod(0o755)

        first = BundleArchive.write(one, tmp_path / "one.tar.gz")
        second = BundleArchive.write(two, tmp_path / "two.tar.gz")

        assert first == second

    def test_the_members_are_sorted_posix_paths_with_no_owner_time_or_private_mode(
        self, tmp_path: Path
    ) -> None:
        staging = self.staged(tmp_path / "s", ["wheels/z.whl", "manifest.json", "plugin/a/b.md"])
        (staging / "empty-directory").mkdir()
        os.utime(staging / "manifest.json", (123456789, 123456789))

        data = BundleArchive.write(staging, tmp_path / "out.tar.gz")

        with tar_of(data) as tar:
            members = tar.getmembers()
        assert [m.name for m in members] == ["manifest.json", "plugin/a/b.md", "wheels/z.whl"]
        for member in members:
            assert member.isfile()
            assert (member.mode, member.uid, member.gid, member.mtime) == (0o644, 0, 0, 0)
            assert (member.uname, member.gname) == ("", "")

    def test_the_gzip_header_carries_no_time_or_file_name(self, tmp_path: Path) -> None:
        data = BundleArchive.write(self.staged(tmp_path / "s", ["manifest.json"]), tmp_path / "o")

        assert data[:2] == b"\x1f\x8b"
        assert data[4:8] == b"\x00\x00\x00\x00"
        assert data[3] == 0, "no FNAME or other optional header field"

    def test_it_answers_the_bytes_it_wrote_and_makes_the_directory(self, tmp_path: Path) -> None:
        staging = self.staged(tmp_path / "s", ["manifest.json"])
        out = tmp_path / "not" / "yet" / "there" / "bundle.tar.gz"

        data = BundleArchive.write(staging, out)

        assert out.read_bytes() == data

    def test_an_empty_staging_directory_is_an_archive_with_no_members(self, tmp_path: Path) -> None:
        (tmp_path / "s").mkdir()

        data = BundleArchive.write(tmp_path / "s", tmp_path / "o.tar.gz")

        with tar_of(data) as tar:
            assert tar.getmembers() == []

    def test_unicode_and_empty_files_travel(self, tmp_path: Path) -> None:
        staging = tmp_path / "s"
        staging.mkdir()
        (staging / "ünï-文件.md").write_text("héllo")
        (staging / "empty").write_bytes(b"")

        data = BundleArchive.write(staging, tmp_path / "o.tar.gz")

        with tar_of(data) as tar:
            names = sorted(m.name for m in tar.getmembers())
            extracted = tar.extractfile("ünï-文件.md")
            assert extracted is not None
            assert extracted.read() == "héllo".encode()
            empty = tar.extractfile("empty")
            assert empty is not None
            assert empty.read() == b""
        assert names == sorted(["ünï-文件.md", "empty"])


class TestReadingTheManifestBack:
    MANIFEST = json.dumps(EXTENSION).encode()

    def test_a_manifest_at_the_root_is_read_without_unpacking(self) -> None:
        archive = gzipped_tar({"wheels/x.whl": b"x", "manifest.json": self.MANIFEST})

        assert BundleArchive.read_manifest(archive) == EXTENSION

    def test_a_dot_slash_prefix_is_accepted(self) -> None:
        assert BundleArchive.read_manifest(gzipped_tar({"./manifest.json": self.MANIFEST})) == (
            EXTENSION
        )

    def test_a_manifest_only_in_a_subdirectory_is_not_the_bundle_s(self) -> None:
        archive = gzipped_tar({"plugin/manifest.json": self.MANIFEST})

        with pytest.raises(BundleError, match="has no manifest.json at its root"):
            BundleArchive.read_manifest(archive)

    def test_a_manifest_that_is_not_a_file_is_not_one(self) -> None:
        archive = gzipped_tar({}, types={"manifest.json": b""})

        with pytest.raises(BundleError, match="has no manifest.json at its root"):
            BundleArchive.read_manifest(archive)

    def test_a_directory_of_that_name_does_not_hide_the_file_after_it(self) -> None:
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w") as tar:
            directory = tarfile.TarInfo("manifest.json")
            directory.type = tarfile.DIRTYPE
            tar.addfile(directory)
            info = tarfile.TarInfo("manifest.json")
            info.size = len(self.MANIFEST)
            tar.addfile(info, io.BytesIO(self.MANIFEST))

        assert BundleArchive.read_manifest(gzip.compress(raw.getvalue())) == EXTENSION

    @pytest.mark.parametrize(
        "body",
        [b"[1, 2]", b"3", b'"text"', b"null", b"{not json", b"\xff\xfe\x00bad", b""],
    )
    def test_a_manifest_that_is_not_a_json_object_is_unreadable(self, body: bytes) -> None:
        with pytest.raises(BundleError, match="the extension bundle is unreadable"):
            BundleArchive.read_manifest(gzipped_tar({"manifest.json": body}))

    @pytest.mark.parametrize("archive", [b"", b"not a gzip at all", gzip.compress(b"not a tar")])
    def test_bytes_that_are_not_a_gzipped_tar_are_unreadable(self, archive: bytes) -> None:
        with pytest.raises(BundleError, match="the extension bundle is unreadable"):
            BundleArchive.read_manifest(archive)

    def test_a_truncated_archive_is_unreadable(self) -> None:
        archive = gzipped_tar({"a": os.urandom(4096), "manifest.json": self.MANIFEST})

        with pytest.raises(BundleError, match="the extension bundle is unreadable"):
            BundleArchive.read_manifest(archive[: len(archive) // 2])

    def test_a_corrupted_archive_is_unreadable_not_a_raw_error(self) -> None:
        archive = bytearray(gzipped_tar({"a": os.urandom(8192), "manifest.json": self.MANIFEST}))
        for index in range(40, len(archive) - 8, 7):
            archive[index] ^= 0xFF

        with pytest.raises(BundleError, match="the extension bundle is unreadable"):
            BundleArchive.read_manifest(bytes(archive))


def test_the_package_docstring_lists_every_module_and_only_those() -> None:
    folder = Path(inspect.getfile(bundle_package)).parent
    on_disk = {
        path.stem for path in folder.glob("*.py") if path.stem not in {"__init__", "__main__"}
    }
    listed = set(re.findall(r"^- `(\w+)` —", bundle_package.__doc__ or "", flags=re.M))

    assert listed == on_disk


class TestThePlatforms:
    def test_the_three_platforms_igni_runs_on_in_their_order(self) -> None:
        assert [(p.name, p.asset.value, p.uv) for p in PLATFORMS] == [
            ("macOS arm64", "macos-arm64", "aarch64-apple-darwin"),
            ("Linux x86_64", "linux-x86_64", "x86_64-manylinux_2_28"),
            ("Windows x86_64", "windows-x86_64", "x86_64-pc-windows-msvc"),
        ]

    def test_linux_runs_from_manylinux_2_28_down_to_the_oldest_then_the_named_ones(self) -> None:
        [linux] = [p for p in PLATFORMS if p.asset.value == "linux-x86_64"]

        assert linux.pip == (
            *(f"manylinux_2_{minor}_x86_64" for minor in (28, 27, 26, 25, 24, 23, 22, 21, 20)),
            *(f"manylinux_2_{minor}_x86_64" for minor in (19, 18, 17)),
            "manylinux2014_x86_64",
            "manylinux2010_x86_64",
            "manylinux1_x86_64",
            "linux_x86_64",
        )
        assert linux.uv_env == ()

    def test_macos_26_is_the_target_for_pip_and_for_uv(self) -> None:
        [mac] = [p for p in PLATFORMS if p.asset.value == "macos-arm64"]

        assert MACOS_TARGET == "26.0"
        assert mac.pip == ("macosx_26_0_arm64",)
        assert mac.uv_env == (("MACOSX_DEPLOYMENT_TARGET", "26.0"),)

    def test_windows_has_one_tag_and_no_uv_environment(self) -> None:
        [windows] = [p for p in PLATFORMS if p.asset.value == "windows-x86_64"]

        assert windows.pip == ("win_amd64",)
        assert windows.uv_env == ()

    def test_pip_gets_one_platform_flag_a_tag_in_order(self) -> None:
        [mac, linux, windows] = PLATFORMS

        assert mac.pip_flags() == ["--platform", "macosx_26_0_arm64"]
        assert windows.pip_flags() == ["--platform", "win_amd64"]
        flags = linux.pip_flags()
        assert flags[0::2] == ["--platform"] * len(linux.pip)
        assert flags[1::2] == list(linux.pip)

    def test_a_platform_cannot_be_changed(self) -> None:
        with pytest.raises(ValidationError):
            PLATFORMS[0].name = "elsewhere"
        assert isinstance(PLATFORMS[0], Platform)


class TestRequirementNames:
    @pytest.mark.parametrize(
        ("name", "normal"),
        [
            ("Some_Pkg.x", "some-pkg-x"),
            ("a--b__c..d", "a-b-c-d"),
            ("ABC", "abc"),
            ("  padded ", "padded"),
            ("a-_.b", "a-b"),
        ],
    )
    def test_names_are_pep_503(self, name: str, normal: str) -> None:
        assert Requirement.normalise(name) == normal

    @pytest.mark.parametrize(
        ("line", "name"),
        [
            ("mcp==1.30.0 --hash=sha256:aa", "mcp"),
            ("Some_Pkg>=1", "some-pkg"),
            ("a<2", "a"),
            ("a!=1", "a"),
            ("a~=1", "a"),
            ("a;python_version<'3.13'", "a"),
            ("a[extra]==1", "a"),
            ("a ==1", "a"),
            ("bare", "bare"),
            ("a>1", "a"),
        ],
    )
    def test_the_name_ends_at_an_operator_extras_marker_or_space(
        self, line: str, name: str
    ) -> None:
        assert Requirement.name_of(line) == name

    @pytest.mark.parametrize(
        ("wheel", "name"),
        [
            ("igni_extension-0.1.0-py3-none-any.whl", "igni-extension"),
            ("Tiny.Dep-1.0.0-cp312-cp312-win_amd64.whl", "tiny-dep"),
            ("plain-1-py3-none-any.whl", "plain"),
        ],
    )
    def test_a_wheel_is_of_the_distribution_its_file_name_starts_with(
        self, wheel: str, name: str
    ) -> None:
        assert Requirement.of_wheel(wheel) == name


class TestHashedRequirementLines:
    def test_empty_text_has_no_requirements(self) -> None:
        assert HashedRequirements.parse("") == []
        assert HashedRequirements.parse("\n  \n") == []

    def test_blanks_comments_and_other_options_are_skipped(self) -> None:
        text = (
            "# comment\n"
            "\n"
            "--index-url https://example.test/simple\n"
            "-e .\n"
            "a==1 \\\n"
            "    # a comment between\n"
            "    --extra-index-url x \\\n"
            "    --hash=sha256:aa\n"
        )

        assert HashedRequirements.parse(text) == ["a==1 --hash=sha256:aa"]

    def test_a_hash_before_any_requirement_is_dropped_not_a_requirement(self) -> None:
        assert HashedRequirements.parse("--hash=sha256:aa\nb==2 \\\n  --hash=sha256:bb\n") == [
            "b==2 --hash=sha256:bb"
        ]

    def test_trailing_backslashes_whitespace_and_crlf_are_dropped(self) -> None:
        text = "a==1 \\  \r\n    --hash=sha256:aa \\ \r\n    --hash=sha256:bb\r\nb==2\r\n"

        assert HashedRequirements.parse(text) == [
            "a==1 --hash=sha256:aa --hash=sha256:bb",
            "b==2",
        ]

    def test_extras_and_markers_stay_on_the_line(self) -> None:
        text = "a[x]==1 ; python_version >= '3.12' \\\n    --hash=sha256:aa\n"

        assert HashedRequirements.parse(text) == [
            "a[x]==1 ; python_version >= '3.12' --hash=sha256:aa"
        ]

    def test_bare_drops_the_hashes_and_leaves_an_unhashed_line_alone(self) -> None:
        assert HashedRequirements.bare("a==1 --hash=sha256:aa --hash=sha256:bb") == "a==1"
        assert HashedRequirements.bare("a==1") == "a==1"

    def test_the_hashes_come_in_the_order_the_line_names_them(self) -> None:
        line = "a==1 --hash=sha256:bb --hash=sha256:aa --hash=sha256:cc"

        assert HashedRequirements.hashes_of(line) == ["bb", "aa", "cc"]

    def test_a_line_with_no_hash_or_a_hash_with_no_colon_pins_nothing(self) -> None:
        assert HashedRequirements.hashes_of("a==1") == []
        assert HashedRequirements.hashes_of("a==1 --hash=nocolon --hash=sha256:aa") == ["aa"]


class TestTheExtensionsPyprojectEdges:
    @staticmethod
    def project(tmp_path: Path, toml: str) -> ExtensionProject:
        (tmp_path / "pyproject.toml").write_text(textwrap.dedent(toml))
        return ExtensionProject.read(tmp_path)

    def test_a_script_that_is_not_a_string_is_refused_in_general_words(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(BundleError) as refused:
            self.project(tmp_path, '[project]\nname = "x"\n[project.scripts]\nx = 3\n')

        assert "[project] needs a name and string [project.scripts]" in str(refused.value)
        assert "must be a list of names" in str(refused.value)

    def test_an_sdist_only_list_of_non_strings_is_refused_in_its_own_words(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(BundleError) as refused:
            self.project(tmp_path, "[tool.igni.bundle]\nsdist-only = [1, 2]\n")

        assert str(refused.value) == "[tool.igni.bundle] sdist-only must be a list of names"

    def test_no_project_table_means_no_name_and_the_package_cannot_match(
        self, tmp_path: Path
    ) -> None:
        project = self.project(tmp_path, "[tool.ruff]\nline-length = 1\n")

        with pytest.raises(BundleError, match="but pyproject.toml builds ''"):
            project.check_package(PythonPackaging(package="acme", entry="acme"))

    def test_the_package_is_compared_by_its_pep_503_name(self, tmp_path: Path) -> None:
        project = self.project(
            tmp_path,
            """\
            [project]
            name = "Acme.Example_Pkg"
            [project.scripts]
            go = "acme:main"
            """,
        )

        project.check_package(PythonPackaging(package="acme-example-pkg", entry="go"))
        with pytest.raises(BundleError) as refused:
            project.check_package(PythonPackaging(package="acme-example", entry="go"))
        assert str(refused.value) == (
            "manifest.json installs 'acme-example' but pyproject.toml builds 'Acme.Example_Pkg'"
        )

    def test_an_entry_the_scripts_do_not_declare_is_refused_in_its_own_words(
        self, tmp_path: Path
    ) -> None:
        project = self.project(
            tmp_path, '[project]\nname = "acme"\n[project.scripts]\ngo = "a:b"\n'
        )

        with pytest.raises(BundleError) as refused:
            project.check_package(PythonPackaging(package="acme", entry="stop"))

        assert str(refused.value) == (
            "manifest.json starts 'stop', which pyproject.toml "
            "does not declare under [project.scripts]"
        )

    def test_a_module_is_trimmed_and_an_entry_with_no_colon_is_the_whole_value(
        self, tmp_path: Path
    ) -> None:
        project = self.project(
            tmp_path,
            """\
            [project]
            name = "acme"
            [project.scripts]
            padded = "  acme.cli  :main"
            bare = "acme.cli"
            """,
        )

        assert project.module_of("padded") == "acme.cli"
        assert project.module_of("bare") == "acme.cli"

    def test_sdist_only_has_no_names_by_default_and_is_read_under_its_dashed_key(
        self, tmp_path: Path
    ) -> None:
        assert self.project(tmp_path, '[project]\nname = "a"\n').sdist_only() == set()
        assert self.project(tmp_path, "[tool.igni.bundle]\nsdist-only = []\n").sdist_only() == set()

    def test_a_pyproject_that_is_not_a_table_of_the_expected_shape_says_where(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(BundleError, match="pyproject.toml"):
            self.project(tmp_path, 'project = "text"\n')


HINTS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


class TestTheManifestTables:
    @staticmethod
    def write(tmp_path: Path, content: str) -> Path:
        path = tmp_path / "manifest.json"
        path.write_text(content)
        return path

    def test_a_missing_file_says_it_does_not_exist(self, tmp_path: Path) -> None:
        path = tmp_path / "manifest.json"

        with pytest.raises(BundleError) as refused:
            BundleManifest.read(path)

        assert str(refused.value) == f"{path} does not exist"

    @pytest.mark.parametrize(
        "content",
        [
            "{not json",
            "[]",
            "3",
            "{}",
            json.dumps({"version": "1", "python": {"package": "a", "entry": "a"}}),
            json.dumps({"id": "a", "python": {"package": "a", "entry": "a"}}),
            json.dumps({"id": "a", "version": "1"}),
            json.dumps({"id": "a", "version": "1", "python": {"package": "a"}}),
            json.dumps({"id": "a", "version": "1", "python": {"entry": "a"}}),
        ],
    )
    def test_a_manifest_that_is_not_the_bundle_s_is_refused_in_one_wording(
        self, tmp_path: Path, content: str
    ) -> None:
        path = self.write(tmp_path, content)

        with pytest.raises(BundleError) as refused:
            BundleManifest.read(path)

        assert str(refused.value).startswith(
            f"{path} must name an id, a version and the `python` packaging, state all four "
            "hints of every tool in permissions.tools, and pin every asset it declares: "
        )

    def test_the_packaging_defaults_its_wheels_directory_and_keeps_other_keys(self) -> None:
        manifest = manifest_of({**EXTENSION, "python": {"package": "a", "entry": "b", "mcp": 1}})

        assert manifest.python.wheels == "wheels"
        assert manifest.python.model_extra == {"mcp": 1}

    @pytest.mark.parametrize("hint", list(HINTS))
    def test_a_tool_must_state_each_of_the_four_hints(self, hint: str) -> None:
        annotations = {k: v for k, v in HINTS.items() if k != hint}

        with pytest.raises(ValidationError, match=hint):
            ToolAnnotations.model_validate(annotations)

    def test_a_hint_that_is_not_a_boolean_or_an_unknown_one_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ToolAnnotations.model_validate({**HINTS, "readOnlyHint": "maybe"})
        with pytest.raises(ValidationError):
            ToolAnnotations.model_validate({**HINTS, "titleHint": "x"})
        with pytest.raises(ValidationError):
            AgentTool.model_validate({"name": "t", "annotations": HINTS, "extra": 1})

    def test_each_differing_hint_is_said_both_ways_in_the_hints_order(self) -> None:
        manifest = ToolAnnotations.model_validate(HINTS)
        code = ToolAnnotations.model_validate(
            {**HINTS, "readOnlyHint": False, "openWorldHint": True}
        )

        assert manifest.differences(code) == [
            "readOnlyHint True in the manifest, False in the code",
            "openWorldHint False in the manifest, True in the code",
        ]
        assert manifest.differences(manifest) == []

    def test_hooks_beside_an_endpoint_are_refused_naming_the_events(self) -> None:
        with pytest.raises(ValidationError) as refused:
            manifest_of(
                {
                    **EXTENSION,
                    "endpoint": {"url": "https://x.test/mcp"},
                    "permissions": {"hooks": ["PreToolUse", "PlanSubmit"]},
                }
            )

        assert "permissions.hooks (PreToolUse, PlanSubmit) needs a process igni starts" in str(
            refused.value
        )

    def test_an_endpoint_alone_and_hooks_alone_are_accepted(self) -> None:
        manifest_of({**EXTENSION, "endpoint": {"url": "https://x.test/mcp"}})
        manifest_of({**EXTENSION, "permissions": {"hooks": ["PreToolUse"]}})
        manifest_of(
            {**EXTENSION, "endpoint": {"url": "https://x.test/mcp"}, "permissions": {"hooks": []}}
        )

    def test_tools_are_declared_when_the_file_says_so_even_as_an_empty_list(self) -> None:
        assert not manifest_of(EXTENSION).declares_tools
        assert not manifest_of({**EXTENSION, "permissions": {}}).declares_tools
        assert not manifest_of({**EXTENSION, "permissions": {"hooks": []}}).declares_tools
        assert manifest_of({**EXTENSION, "permissions": {"tools": []}}).declares_tools
        assert manifest_of({**EXTENSION, "permissions": {"tools": [LOOKUP]}}).declares_tools

    def test_a_name_is_qualified_under_the_id_unless_it_already_is(self) -> None:
        manifest = manifest_of(EXTENSION)

        assert manifest.qualified("lookup") == "acme.example.lookup"
        assert manifest.qualified("acme.example.lookup") == "acme.example.lookup"
        assert manifest.qualified("acme.examplelookup") == "acme.example.acme.examplelookup"

    def test_with_tools_replaces_them_and_leaves_the_original_alone(self) -> None:
        original = manifest_of({**EXTENSION, "permissions": {"tools": [LOOKUP]}})

        replaced = original.with_tools([])

        assert replaced.permissions.tools == []
        assert [t.name for t in original.permissions.tools] == ["acme.example.lookup"]

    def test_the_manifest_is_written_as_the_file_said_it_two_space_indented(self) -> None:
        raw = {**EXTENSION, "name": "Example", "zzz": {"kept": [1, 2]}}

        written = manifest_of(raw).to_json()

        assert written == json.dumps(raw, indent=2) + "\n"
        assert json.loads(written) == raw

    def test_a_declared_empty_tool_list_is_written_and_absent_defaults_are_not(self) -> None:
        raw = {**EXTENSION, "permissions": {"tools": []}}

        assert json.loads(manifest_of(raw).to_json()) == raw

    def test_assets_must_cover_every_platform(self) -> None:
        one = {
            "name": "jre",
            "platform": "macos-arm64",
            "file": "jre.tar.gz",
            "size": 1,
            "sha256": "0" * 64,
            "source": "https://x.test/jre.tar.gz",
        }
        with pytest.raises(ValidationError, match="one for each of"):
            manifest_of({**EXTENSION, "assets": [one]})
        assert manifest_of({**EXTENSION, "assets": []}).assets == []


def code_of(*names: str, hints: dict[str, bool] | None = None) -> CodeToolsRead:
    return CodeToolsRead(
        tools=[
            AgentTool.model_validate({"name": name, "annotations": hints or HINTS})
            for name in names
        ]
    )


class TestPermissionsToolsSaysEverythingWrong:
    def test_several_problems_come_in_one_refusal_in_the_declaration_s_order(self) -> None:
        flipped = {**HINTS, "readOnlyHint": False, "idempotentHint": False}
        manifest = manifest_of(
            {
                **EXTENSION,
                "permissions": {
                    "tools": [
                        {"name": "gone", "annotations": HINTS},
                        {"name": "differs", "annotations": HINTS},
                        {"name": "fine", "annotations": HINTS},
                    ]
                },
            }
        )
        code = CodeToolsRead(
            tools=[
                AgentTool.model_validate({"name": "acme.example.differs", "annotations": flipped}),
                AgentTool.model_validate({"name": "acme.example.fine", "annotations": HINTS}),
            ]
        )

        with pytest.raises(BundleError) as refused:
            PermissionsTools(manifest).against(code)

        assert str(refused.value) == (
            "permissions.tools does not say what the code does:\n"
            "  gone: declared, and the code does not register it\n"
            "  differs: readOnlyHint True in the manifest, False in the code; "
            "idempotentHint True in the manifest, False in the code\n"
            "Fix the manifest, or leave permissions.tools out and the builder "
            "writes it from the code."
        )

    def test_the_tools_the_declaration_leaves_out_are_said_sorted(self) -> None:
        manifest = manifest_of({**EXTENSION, "permissions": {"tools": []}})

        outcome = PermissionsTools(manifest).against(
            code_of("acme.example.zeta", "acme.example.alpha", "acme.example.mid")
        )

        assert outcome.written is None
        assert outcome.notes == [
            "not offered to the agent (registered, not in permissions.tools): "
            "acme.example.alpha, acme.example.mid, acme.example.zeta"
        ]

    def test_a_declaration_that_covers_the_code_says_nothing(self) -> None:
        manifest = manifest_of(
            {
                **EXTENSION,
                "permissions": {"tools": [{"name": "acme.example.a", "annotations": HINTS}]},
            }
        )

        outcome = PermissionsTools(manifest).against(code_of("acme.example.a"))

        assert outcome.written is None and outcome.notes == []

    def test_the_written_note_names_each_tool_in_the_code_s_order(self) -> None:
        outcome = PermissionsTools(manifest_of(EXTENSION)).against(
            code_of("acme.example.b", "acme.example.a")
        )

        assert outcome.written is not None
        assert outcome.notes == [
            "permissions.tools written from the code: acme.example.b, acme.example.a"
        ]

    def test_nothing_read_and_no_problem_is_silent_with_or_without_a_declaration(self) -> None:
        declared = manifest_of({**EXTENSION, "permissions": {"tools": [LOOKUP]}})

        for manifest in (manifest_of(EXTENSION), declared):
            outcome = PermissionsTools(manifest).against(CodeToolsRead())
            assert outcome.written is None and outcome.notes == []

    def test_nothing_read_with_a_problem_and_no_declaration_says_the_agent_is_offered_none(
        self,
    ) -> None:
        outcome = PermissionsTools(manifest_of(EXTENSION)).against(CodeToolsRead(problem="boom"))

        assert outcome.written is None
        assert outcome.notes == [
            "could not read the tools from the code (boom), and the manifest "
            "declares no permissions.tools: the agent is offered none of its tools. "
            "Build on a platform the bundle includes, or declare them."
        ]
