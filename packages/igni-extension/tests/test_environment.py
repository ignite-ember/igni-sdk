"""`ExtensionEnvironment`: what igni's variables say, read once and typed.

test_extension.py reads a full environment through `IgniExtension`; these
are the edges: what an unset, blank or odd variable means, and what each
typed part answers.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from igni_extension import (
    ExtensionEnvironment,
    HostEndpoint,
    NotConfigured,
    Secrets,
    Workspace,
    WorkspaceMode,
)


def _read(**variables: str) -> ExtensionEnvironment:
    return ExtensionEnvironment.read(variables)


class TestWorkspace:
    def test_a_root_alone_is_read_only(self, tmp_path: Path) -> None:
        workspace = _read(IGNI_WORKSPACE=str(tmp_path)).workspace

        assert workspace.mode is WorkspaceMode.READ
        assert workspace.granted and not workspace.writable

    def test_a_write_grant_is_writable(self, tmp_path: Path) -> None:
        workspace = _read(IGNI_WORKSPACE=str(tmp_path), IGNI_WORKSPACE_MODE="write").workspace

        assert workspace.granted and workspace.writable

    def test_mode_none_with_a_root_grants_nothing(self, tmp_path: Path) -> None:
        workspace = _read(IGNI_WORKSPACE=str(tmp_path), IGNI_WORKSPACE_MODE="none").workspace

        assert workspace.root == tmp_path
        assert not workspace.granted and not workspace.writable

    def test_a_mode_it_does_not_know_falls_back_to_read(self, tmp_path: Path) -> None:
        for odd in ("WRITE", "admin", "rw"):
            workspace = _read(IGNI_WORKSPACE=str(tmp_path), IGNI_WORKSPACE_MODE=odd).workspace

            assert workspace.mode is WorkspaceMode.READ, odd
            assert not workspace.writable

    def test_a_mode_with_blanks_around_it_is_trimmed_and_a_blank_one_is_read(
        self, tmp_path: Path
    ) -> None:
        trimmed = _read(IGNI_WORKSPACE=str(tmp_path), IGNI_WORKSPACE_MODE="  write ").workspace
        blank = _read(IGNI_WORKSPACE=str(tmp_path), IGNI_WORKSPACE_MODE="   ").workspace

        assert trimmed.mode is WorkspaceMode.WRITE
        assert blank.mode is WorkspaceMode.READ

    def test_a_mode_without_a_root_is_ignored(self) -> None:
        workspace = _read(IGNI_WORKSPACE_MODE="write", IGNI_WORKSPACE_PATHS="src/**").workspace

        assert workspace == Workspace()
        assert not workspace.granted and workspace.mode is WorkspaceMode.NONE

    def test_a_blank_root_is_no_root(self) -> None:
        assert _read(IGNI_WORKSPACE="   ").workspace == Workspace()

    def test_the_paths_drop_empty_segments(self, tmp_path: Path) -> None:
        workspace = _read(
            IGNI_WORKSPACE=str(tmp_path), IGNI_WORKSPACE_PATHS=":docs/**::src:"
        ).workspace

        assert workspace.paths == ("docs/**", "src")

    def test_no_paths_means_the_whole_project(self, tmp_path: Path) -> None:
        assert _read(IGNI_WORKSPACE=str(tmp_path)).workspace.paths == ()

    def test_a_granted_workspace_is_frozen(self, tmp_path: Path) -> None:
        workspace = _read(IGNI_WORKSPACE=str(tmp_path)).workspace

        with pytest.raises(ValidationError):
            workspace.mode = WorkspaceMode.WRITE


class TestSecrets:
    def test_a_name_is_written_the_way_igni_writes_its_variable(self) -> None:
        assert Secrets.env_name("ledger-token") == "LEDGER_TOKEN"
        assert Secrets.env_name("a.b/c d") == "A_B_C_D"
        assert Secrets.env_name("key2") == "KEY2"
        assert Secrets.env_name("clé") == "CLÉ"

    def test_a_secret_is_found_by_the_manifests_name(self) -> None:
        secrets = _read(IGNI_SECRET_LEDGER_TOKEN="ledger", OTHER="no").secrets

        assert secrets.get("ledger-token") == "ledger"
        assert secrets.get("LEDGER_TOKEN") == "ledger"
        assert secrets.get("other") is None

    def test_an_empty_secret_is_empty_not_missing(self) -> None:
        assert _read(IGNI_SECRET_EMPTY="").secrets.get("empty") == ""

    def test_the_value_is_not_trimmed(self) -> None:
        assert _read(IGNI_SECRET_PADDED=" v ").secrets.get("padded") == " v "


class TestService:
    def test_the_url_is_trimmed_and_loses_every_trailing_slash(self) -> None:
        service = _read(IGNI_SERVICE_URL="  https://acme.example.test///  ").service

        assert service.url == "https://acme.example.test"
        assert service.configured

    def test_the_token_endpoint_and_its_secret_are_read_trimmed(self) -> None:
        service = _read(
            IGNI_SERVICE_URL="https://acme.example.test",
            IGNI_SERVICE_TOKEN_URL=" http://127.0.0.1:9/token ",
            IGNI_SERVICE_TOKEN_SECRET=" s3cret ",
        ).service

        assert service.token_url == "http://127.0.0.1:9/token"
        assert service.token_secret == "s3cret"

    def test_a_blank_url_is_no_service(self) -> None:
        assert not _read(IGNI_SERVICE_URL="  ").service.configured


class TestHost:
    def test_it_needs_both_the_address_and_the_secret(self) -> None:
        assert _read(IGNI_HOST_URL="ws://h", IGNI_HOST_SECRET="s").host.configured
        assert not _read(IGNI_HOST_URL="ws://h").host.configured
        assert not _read(IGNI_HOST_SECRET="s").host.configured
        assert not _read().host.configured

    def test_both_are_trimmed_and_a_blank_one_is_unset(self) -> None:
        host = _read(IGNI_HOST_URL=" ws://h ", IGNI_HOST_SECRET=" s ").host

        assert host == HostEndpoint(url="ws://h", secret="s")
        assert not _read(IGNI_HOST_URL="ws://h", IGNI_HOST_SECRET="  ").host.configured


class TestDataAndEnvironSource:
    def test_a_blank_data_dir_is_none(self) -> None:
        assert _read(IGNI_EXTENSION_DATA="  ").data_dir is None
        assert _read().data_dir is None

    def test_the_data_dir_is_a_path(self, tmp_path: Path) -> None:
        assert _read(IGNI_EXTENSION_DATA=f" {tmp_path} ").data_dir == tmp_path

    def test_without_a_mapping_it_reads_the_process_environment(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("IGNI_EXTENSION_DATA", str(tmp_path))
        monkeypatch.setenv("IGNI_HOST_URL", "ws://h")
        monkeypatch.setenv("IGNI_HOST_SECRET", "s")
        monkeypatch.setenv("IGNI_SECRET_FROM_OS", "yes")

        environment = ExtensionEnvironment.read()

        assert environment.data_dir == tmp_path
        assert environment.host.configured
        assert environment.secrets.get("from-os") == "yes"

    def test_a_mapping_given_hides_the_process_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IGNI_HOST_URL", "ws://h")
        monkeypatch.setenv("IGNI_SECRET_FROM_OS", "yes")

        environment = ExtensionEnvironment.read({})

        assert not environment.host.configured
        assert environment.secrets.get("from-os") is None

    def test_the_whole_environment_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            _read().data_dir = Path("/x")


class TestAssets:
    @pytest.fixture
    def root(self, tmp_path: Path) -> Path:
        root = tmp_path / "assets"
        (root / "model").mkdir(parents=True)
        (root / "model" / "model.onnx").write_bytes(b"onnx")
        (root / "model" / "conf").mkdir()
        (root / "model" / "conf" / "a.conf").write_text("a")
        (root / "other").mkdir()
        (root / "other" / "secret.txt").write_text("not the model's")
        (root / "plain-file").write_text("not a directory")
        return root

    def _assets(self, root: Path) -> ExtensionEnvironment:
        return _read(IGNI_EXTENSION_ASSETS=str(root))

    def test_a_blank_assets_variable_is_no_assets(self) -> None:
        environment = _read(IGNI_EXTENSION_ASSETS="  ")

        assert environment.assets.root is None
        with pytest.raises(NotConfigured, match="laid out no assets"):
            environment.assets.path("model")

    def test_an_asset_that_is_a_file_is_not_an_asset(self, root: Path) -> None:
        with pytest.raises(NotConfigured, match="no asset named 'plain-file'"):
            self._assets(root).assets.path("plain-file")

    def test_a_file_that_is_a_directory_is_not_a_file(self, root: Path) -> None:
        with pytest.raises(NotConfigured, match="has no file 'conf'"):
            self._assets(root).assets.file("model", "conf")

    def test_a_file_inside_the_asset_may_be_nested(self, root: Path) -> None:
        assert self._assets(root).assets.file("model", "conf/a.conf") == (
            root / "model" / "conf" / "a.conf"
        )

    @pytest.mark.parametrize("name", ["..", "../other", "model/..", "model/conf", ".", ""])
    def test_a_name_that_leaves_the_root_or_is_not_one_directory_names_no_asset(
        self, root: Path, name: str
    ) -> None:
        with pytest.raises(NotConfigured, match="no asset named"):
            self._assets(root).assets.path(name)

    def test_an_absolute_name_names_no_asset(self, root: Path) -> None:
        elsewhere = root.parent / "elsewhere"
        elsewhere.mkdir()

        with pytest.raises(NotConfigured, match="no asset named"):
            self._assets(root).assets.path(str(elsewhere))

    @pytest.mark.parametrize("file", ["../other/secret.txt", "conf/../../other/secret.txt"])
    def test_a_file_outside_the_asset_is_not_one_of_its_files(self, root: Path, file: str) -> None:
        with pytest.raises(NotConfigured, match="has no file"):
            self._assets(root).assets.file("model", file)

    def test_an_absolute_file_is_not_one_of_the_assets_files(self, root: Path) -> None:
        with pytest.raises(NotConfigured, match="has no file"):
            self._assets(root).assets.file("model", str(root / "other" / "secret.txt"))

    def test_a_root_spelled_with_dots_still_finds_its_assets(self, root: Path) -> None:
        spelled = root / "model" / ".." / "."
        environment = _read(IGNI_EXTENSION_ASSETS=str(spelled))

        assert environment.assets.path("model") == spelled / "model"
        assert environment.assets.file("model", "model.onnx").name == "model.onnx"
