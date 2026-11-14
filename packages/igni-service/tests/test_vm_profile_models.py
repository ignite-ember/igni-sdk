"""The VM profile models: what a request may hold, what igni's answers are read as, and refusal()."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from igni_service import IgniUnavailable, VmPackages, VmProfileRefused, VmProfileRequest
from igni_service.testing import FakeIgni
from igni_service.vm_profiles import (
    MAX_PACKAGES,
    MAX_SETUP_SCRIPT,
    AppVmProfile,
    Assigned,
    EffectiveVmProfile,
    RequestedVmProfile,
    ServiceVmProfile,
    VmProfileRequestRecord,
    refusal,
)

from .answers import answer
from .conftest import ORG

LIMIT_NAME = "p" * 200


def ask(**fields: Any) -> VmProfileRequest:
    return VmProfileRequest(**fields)


def refused(**fields: Any) -> None:
    with pytest.raises(ValidationError):
        VmProfileRequest(**fields)


class TestAPackageIsOneWordToItsManager:
    @pytest.mark.parametrize(
        "name",
        [
            "chromium",
            "requests==2.32.3",
            "@playwright/mcp@0.0.41",
            "libfoo-dev:amd64",
            "numpy>=1.0,<2",
            "pkg~=1.4",
            "a",
            "@scope/pkg",
            "9lives",
            LIMIT_NAME,
        ],
    )
    def test_names_a_manager_knows_are_kept(self, name: str) -> None:
        assert VmPackages(apt=[name]).apt == [name]

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "   ",
            "p" * 201,
            "-rf",
            "--index-url=x",
            ".hidden",
            "/abs/path",
            "two words",
            "a;b",
            "a|b",
            "a&b",
            "$(id)",
            "`id`",
            "a\nb",
            "a\tb",
            'a"b',
            "a'b",
            "a\\b",
            "a#b",
            "a>b>c;",
            "ünïcode",
        ],
    )
    def test_anything_a_shell_would_read_as_more_is_refused(self, name: str) -> None:
        for manager in ("apt", "pip", "npm"):
            with pytest.raises(ValidationError):
                VmPackages(**{manager: [name]})

    def test_blanks_around_a_name_are_stripped(self) -> None:
        assert VmPackages(pip=["  requests==2  ", "\tflask\n"]).pip == ["requests==2", "flask"]

    def test_the_longest_name_is_200_characters(self) -> None:
        assert VmPackages(npm=["x" * 200]).npm[0] == "x" * 200
        with pytest.raises(ValidationError):
            VmPackages(npm=["x" * 201])

    def test_each_manager_takes_200_packages_and_not_201(self) -> None:
        assert MAX_PACKAGES == 200
        for manager in ("apt", "pip", "npm"):
            assert len(VmPackages(**{manager: ["p"] * 200}).model_dump()[manager]) == 200
            with pytest.raises(ValidationError):
                VmPackages(**{manager: ["p"] * 201})

    def test_a_manager_that_does_not_exist_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            VmPackages(gem=["rails"])  # type: ignore[call-arg]

    def test_no_packages_is_three_empty_lists(self) -> None:
        assert VmPackages().model_dump() == {"apt": [], "pip": [], "npm": []}


class TestWhatARequestMayAsk:
    def test_every_field_is_optional_and_nothing_set_sends_nothing(self) -> None:
        assert VmProfileRequest().body() == {}

    def test_only_what_was_set_is_sent_and_none_set_is_sent_as_null(self) -> None:
        body = VmProfileRequest(
            vcpus=2, idle_before_pause_s=None, erase_after_idle_days=None
        ).body()

        assert body == {"vcpus": 2, "idle_before_pause_s": None, "erase_after_idle_days": None}

    def test_packages_are_sent_as_the_managers_that_were_set(self) -> None:
        body = VmProfileRequest(packages=VmPackages(apt=["chromium"])).body()

        assert body == {"packages": {"apt": ["chromium"]}}

    @pytest.mark.parametrize("field", ["memory_mib", "normal_memory_mib", "expected_memory_mib"])
    def test_memory_is_128_to_a_tebibyte_in_mib(self, field: str) -> None:
        assert ask(**{field: 128}).body() == {field: 128}
        assert ask(**{field: 1_048_576}).body() == {field: 1_048_576}
        refused(**{field: 127})
        refused(**{field: 1_048_577})
        refused(**{field: 0})
        refused(**{field: -1})

    def test_vcpus_are_1_to_256(self) -> None:
        assert VmProfileRequest(vcpus=1).vcpus == 1
        assert VmProfileRequest(vcpus=256).vcpus == 256
        refused(vcpus=0)
        refused(vcpus=257)

    def test_idle_time_may_be_zero_and_not_negative(self) -> None:
        assert VmProfileRequest(idle_before_pause_s=0).body() == {"idle_before_pause_s": 0}
        refused(idle_before_pause_s=-1)

    @pytest.mark.parametrize("field", ["volume_gib", "volume_max_gib"])
    def test_a_volume_is_at_least_one_gib(self, field: str) -> None:
        assert ask(**{field: 1}).body() == {field: 1}
        refused(**{field: 0})
        refused(**{field: -5})

    def test_erasing_after_idle_is_1_to_3650_days(self) -> None:
        assert VmProfileRequest(erase_after_idle_days=1).erase_after_idle_days == 1
        assert VmProfileRequest(erase_after_idle_days=3650).erase_after_idle_days == 3650
        refused(erase_after_idle_days=0)
        refused(erase_after_idle_days=3651)

    def test_a_setup_script_is_at_most_65536_characters(self) -> None:
        assert MAX_SETUP_SCRIPT == 65536
        assert len(VmProfileRequest(setup_script="x" * 65536).setup_script or "") == 65536
        refused(setup_script="x" * 65537)
        assert VmProfileRequest(setup_script=None).body() == {"setup_script": None}

    def test_a_field_igni_does_not_know_is_refused_before_sending(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            VmProfileRequest(gpus=1)  # type: ignore[call-arg]

    def test_internet_is_only_a_yes_or_a_no(self) -> None:
        assert VmProfileRequest(internet=True).body() == {"internet": True}
        refused(internet="sometimes")

    def test_a_number_that_is_text_is_refused_not_guessed(self) -> None:
        refused(vcpus="two")
        refused(memory_mib=1024.5)


RECORD: dict[str, Any] = {
    "id": "req-1",
    "org_id": ORG,
    "subject": {"kind": "app", "id": "app-1", "name": "Bot"},
    "state": "pending",
    "requested": {
        "memory_mib": 1024,
        "normal_memory_mib": 512,
        "vcpus": 1,
        "volume_gib": 10,
        "volume_max_gib": 50,
    },
    "version": "v1",
    "packages_version": "pv1",
    "within_caps": True,
    "requested_by": {"kind": "app", "id": "app-1"},
    "requested_at": "2026-11-01T10:00:00Z",
}


class TestWhatIgniAnswersIsRead:
    @pytest.mark.parametrize(
        ("state", "pending", "approved", "rejected"),
        [
            ("pending", True, False, False),
            ("approved", False, True, False),
            ("rejected", False, False, True),
        ],
    )
    def test_a_request_is_in_exactly_one_state(
        self, state: str, pending: bool, approved: bool, rejected: bool
    ) -> None:
        record = VmProfileRequestRecord.model_validate(RECORD | {"state": state})

        assert (record.is_pending, record.is_approved, record.is_rejected) == (
            pending,
            approved,
            rejected,
        )

    @pytest.mark.parametrize("state", ["Pending", "canceled", "", None])
    def test_a_state_igni_does_not_have_is_not_read(self, state: object) -> None:
        with pytest.raises(ValidationError):
            VmProfileRequestRecord.model_validate(RECORD | {"state": state})

    def test_a_pending_request_has_no_decision_and_a_requested_one_has_defaults(self) -> None:
        record = VmProfileRequestRecord.model_validate(RECORD)

        assert record.decided_by is None and record.decided_at is None
        assert record.reason is None and record.profile_id is None
        assert record.requested.packages == VmPackages()
        assert record.requested.internet is False
        assert record.requested.setup_script is None
        assert record.requested.expected_memory_mib is None
        assert record.requested.idle_before_pause_s is None

    def test_times_are_read_as_moments(self) -> None:
        record = VmProfileRequestRecord.model_validate(
            RECORD
            | {
                "state": "rejected",
                "decided_at": "2026-11-02T08:30:00+01:00",
                "decided_by": {"kind": "user", "id": "u-1", "acting_as": "org_admin"},
                "reason": "too much",
            }
        )

        assert record.requested_at == datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
        assert record.decided_at == datetime(2026, 11, 2, 7, 30, tzinfo=UTC)
        assert record.decided_by is not None and record.decided_by.acting_as == "org_admin"
        assert record.is_rejected and record.reason == "too much"

    def test_a_subject_that_is_neither_an_app_nor_an_extension_is_not_read(self) -> None:
        with pytest.raises(ValidationError):
            VmProfileRequestRecord.model_validate(
                RECORD | {"subject": {"kind": "group", "id": "g"}}
            )

    def test_a_record_missing_what_igni_always_sends_is_not_read(self) -> None:
        for gone in ("id", "org_id", "subject", "requested", "version", "within_caps"):
            with pytest.raises(ValidationError):
                VmProfileRequestRecord.model_validate(
                    {k: v for k, v in RECORD.items() if k != gone}
                )

    def test_an_effective_profile_without_the_newer_fields_is_internal_only_and_empty(self) -> None:
        profile = EffectiveVmProfile.model_validate(
            {
                "profile_id": "p",
                "profile_name": "Standard",
                "memory_mib": 2048,
                "normal_memory_mib": 1024,
                "vcpus": 2,
                "volume_max_gib": 50,
            }
        )

        assert profile.internet is False
        assert profile.packages == VmPackages()
        assert profile.expected_memory_mib is None and profile.setup_script is None
        assert profile.idle_before_pause_s is None and profile.erase_after_idle_days is None

    def test_an_app_profile_is_an_effective_one_with_its_volume(self) -> None:
        base = {
            "profile_id": "p",
            "profile_name": "Standard",
            "memory_mib": 2048,
            "normal_memory_mib": 1024,
            "vcpus": 2,
            "volume_max_gib": 50,
        }
        profile = AppVmProfile.model_validate(base | {"volume_gib": 12, "internet": True})

        assert isinstance(profile, EffectiveVmProfile)
        assert (profile.volume_gib, profile.internet) == (12, True)
        with pytest.raises(ValidationError):
            AppVmProfile.model_validate(base)

    def test_a_requested_profile_needs_what_would_run(self) -> None:
        with pytest.raises(ValidationError):
            RequestedVmProfile.model_validate({"memory_mib": 1024})

    def test_who_was_given_a_profile_counts_from_zero(self) -> None:
        assert Assigned().model_dump() == {"groups": 0, "apps": 0}
        assert ServiceVmProfile(org_id=ORG).assigned == Assigned()
        empty = ServiceVmProfile(org_id=ORG)
        assert (empty.extension_id, empty.request, empty.profile) == (None, None, None)


def reply(response: httpx.Response) -> httpx.Response:
    return response


class TestRefusalIsIgnisOwnWords:
    def test_a_detail_is_what_igni_said(self) -> None:
        response = httpx.Response(400, json={"detail": "over the cap"})

        said = refusal(response)

        assert isinstance(said, VmProfileRefused)
        assert (said.status, said.detail) == (400, "over the cap")
        assert str(said) == "igni refused the VM profile request: 400 over the cap"

    @pytest.mark.parametrize(
        ("response", "detail"),
        [
            (httpx.Response(422, text="<html>nope</html>"), "<html>nope</html>"),
            (httpx.Response(403, text=""), ""),
            (httpx.Response(400, json=["a", "list"]), '["a","list"]'),
            (httpx.Response(400, text="null"), "null"),
            (httpx.Response(400, json={"error": "x"}), '{"error":"x"}'),
            (httpx.Response(400, json="plain"), '"plain"'),
        ],
        ids=["not-json", "empty", "list", "null", "no-detail", "string"],
    )
    def test_without_a_detail_it_is_the_body(self, response: httpx.Response, detail: str) -> None:
        said = refusal(response)

        assert said.detail == detail
        assert said.status == response.status_code

    def test_a_detail_that_is_not_text_is_written_as_text(self) -> None:
        said = refusal(httpx.Response(422, json={"detail": [{"loc": ["body"], "msg": "bad"}]}))

        assert said.detail == "[{'loc': ['body'], 'msg': 'bad'}]"


class TestAServiceReadsItsProfileOrSaysIgniIsUnavailable:
    async def read(self, fake: FakeIgni) -> ServiceVmProfile:
        return await fake.service().host(ORG).extension_vm_profile()

    @pytest.mark.parametrize("status", [201, 204, 301, 404, 429, 500, 503])
    async def test_anything_but_a_200_is_igni_unavailable(
        self, fake: FakeIgni, monkeypatch: pytest.MonkeyPatch, status: int
    ) -> None:
        from igni_service.urls import IgniPaths

        answer(monkeypatch, IgniPaths.SERVICE_VM_PROFILE, lambda: httpx.Response(status, json={}))

        with pytest.raises(IgniUnavailable, match=f"igni answered the VM profile read {status}"):
            await self.read(fake)

    @pytest.mark.parametrize(
        "reply",
        [
            lambda: httpx.Response(200, text="<html>nginx</html>"),
            lambda: httpx.Response(200, text=""),
            lambda: httpx.Response(200, json=["a list"]),
            lambda: httpx.Response(200, json=None),
            lambda: httpx.Response(200, json={}),
            lambda: httpx.Response(200, json={"org_id": ORG, "request": {"id": 1}}),
        ],
        ids=["not-json", "empty", "list", "null", "no-org", "bad-request"],
    )
    async def test_a_200_that_is_not_a_profile_is_igni_unavailable(
        self, fake: FakeIgni, monkeypatch: pytest.MonkeyPatch, reply: Any
    ) -> None:
        from igni_service.urls import IgniPaths

        answer(monkeypatch, IgniPaths.SERVICE_VM_PROFILE, reply)

        with pytest.raises(IgniUnavailable, match="with something else") as raised:
            await self.read(fake)

        assert raised.value.__cause__ is not None

    async def test_a_minimal_answer_is_a_profile_with_nothing_asked(
        self, fake: FakeIgni, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from igni_service.urls import IgniPaths

        answer(
            monkeypatch,
            IgniPaths.SERVICE_VM_PROFILE,
            lambda: httpx.Response(200, json={"org_id": ORG}),
        )

        read = await self.read(fake)

        assert read == ServiceVmProfile(org_id=ORG)
