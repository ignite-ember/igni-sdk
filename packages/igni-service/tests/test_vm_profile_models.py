"""The VM profile models and reader on their own: bounds, wire parsing, refusals, errors."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import httpx
import pytest
from pydantic import ValidationError

from igni_service import IgniUnavailable, VmPackages, VmProfileRefused, VmProfileRequest
from igni_service.service_tokens import ServiceTokens
from igni_service.urls import IgniPaths
from igni_service.vm_profiles import (
    MAX_PACKAGES,
    MAX_SETUP_SCRIPT,
    AppVmProfile,
    EffectiveVmProfile,
    RequestedVmProfile,
    ServiceVmProfile,
    ServiceVmProfiles,
    VmProfileRequestRecord,
    refusal,
)

PROFILE: dict[str, Any] = {
    "profile_id": "p-1",
    "profile_name": "Standard",
    "memory_mib": 2048,
    "normal_memory_mib": 1024,
    "vcpus": 2,
    "volume_max_gib": 20,
}
REQUESTED: dict[str, Any] = {
    "memory_mib": 2048,
    "normal_memory_mib": 1024,
    "vcpus": 2,
    "volume_gib": 10,
    "volume_max_gib": 20,
}


def record(**changes: Any) -> dict[str, Any]:
    wire: dict[str, Any] = {
        "id": "r-1",
        "org_id": "org-acme",
        "subject": {"kind": "app", "id": "app-1"},
        "state": "pending",
        "requested": REQUESTED,
        "version": "v1",
        "packages_version": "pv1",
        "within_caps": True,
        "requested_by": {"kind": "app", "id": "app-1"},
        "requested_at": "2026-01-02T03:04:05Z",
    }
    return wire | changes


def refused(wire: dict[str, Any]) -> bool:
    try:
        VmProfileRequest(**wire)
    except ValidationError:
        return True
    return False


@pytest.mark.parametrize(
    ("field", "low", "high"),
    [
        ("memory_mib", 128, 1_048_576),
        ("normal_memory_mib", 128, 1_048_576),
        ("expected_memory_mib", 128, 1_048_576),
        ("vcpus", 1, 256),
        ("erase_after_idle_days", 1, 3650),
    ],
)
def test_a_bounded_field_takes_its_edges_and_refuses_one_beyond(
    field: str, low: int, high: int
) -> None:
    assert not refused({field: low}) and not refused({field: high})
    assert refused({field: low - 1}) and refused({field: high + 1})


@pytest.mark.parametrize(
    ("field", "minimum"),
    [("idle_before_pause_s", 0), ("volume_gib", 1), ("volume_max_gib", 1)],
)
def test_a_field_with_only_a_floor_takes_it_and_refuses_below(field: str, minimum: int) -> None:
    assert not refused({field: minimum}) and not refused({field: 10**9})
    assert refused({field: minimum - 1})


def test_the_setup_script_may_be_65536_characters_and_not_one_more() -> None:
    assert MAX_SETUP_SCRIPT == 65536
    assert not refused({"setup_script": "x" * 65536})
    assert not refused({"setup_script": "é" * 65536})
    assert refused({"setup_script": "x" * 65537})
    assert not refused({"setup_script": ""})


def test_a_manager_may_list_200_packages_and_not_201() -> None:
    assert MAX_PACKAGES == 200
    for manager in ("apt", "pip", "npm"):
        assert len(VmPackages(**{manager: ["p"] * 200}).model_dump()[manager]) == 200
        with pytest.raises(ValidationError):
            VmPackages(**{manager: ["p"] * 201})


def test_a_manager_igni_does_not_know_is_refused_in_packages_and_in_the_request() -> None:
    with pytest.raises(ValidationError):
        VmPackages(cargo=["ripgrep"])  # type: ignore[call-arg]
    assert refused({"packages": {"cargo": ["ripgrep"]}})


def test_the_request_refuses_a_field_it_does_not_have() -> None:
    assert refused({"gpus": 1})
    with pytest.raises(ValidationError):
        VmProfileRequest(vcpu=2)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "name", ["chromium", "requests==2.32.3", "@playwright/mcp@0.0.41", "a" * 200]
)
def test_a_package_as_its_manager_names_it_is_taken(name: str) -> None:
    assert VmPackages(apt=[name]).apt == [name]


def test_a_package_has_its_whitespace_stripped() -> None:
    assert VmPackages(apt=["  chromium\n"]).apt == ["chromium"]


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "two words",
        "a;b",
        "a$(b)",
        "a`b`",
        "-rf",
        "-",
        "a|b",
        "a&b",
        "a\nb",
        "a" * 201,
        ".x",
    ],
)
def test_a_package_a_shell_would_read_as_more_than_one_word_is_refused(name: str) -> None:
    with pytest.raises(ValidationError):
        VmPackages(apt=[name])


def test_the_body_holds_only_what_was_set_including_an_explicit_none() -> None:
    assert VmProfileRequest().body() == {}
    assert VmProfileRequest(vcpus=2).body() == {"vcpus": 2}
    assert VmProfileRequest(idle_before_pause_s=None).body() == {"idle_before_pause_s": None}
    assert VmProfileRequest(idle_before_pause_s=0).body() == {"idle_before_pause_s": 0}
    assert VmProfileRequest(internet=False).body() == {"internet": False}
    assert VmProfileRequest(packages=VmPackages(pip=["requests"])).body() == {
        "packages": {"pip": ["requests"]}
    }


def test_a_request_as_igni_resolved_it_defaults_what_igni_leaves_out() -> None:
    requested = RequestedVmProfile.model_validate(REQUESTED)

    assert requested.internet is False
    assert requested.expected_memory_mib is None
    assert requested.idle_before_pause_s is None
    assert requested.erase_after_idle_days is None
    assert requested.setup_script is None
    assert requested.packages == VmPackages()


def test_igni_s_newer_fields_are_ignored_not_refused() -> None:
    profile = EffectiveVmProfile.model_validate(PROFILE | {"gpus": 4})
    answer = ServiceVmProfile.model_validate({"org_id": "o", "hint": "later"})

    assert profile.internet is False and profile.profile_id == "p-1"
    assert answer.org_id == "o"


def test_an_app_profile_is_an_effective_one_with_its_volume() -> None:
    app = AppVmProfile.model_validate(PROFILE | {"volume_gib": 12, "internet": True})

    assert isinstance(app, EffectiveVmProfile)
    assert (app.volume_gib, app.internet) == (12, True)
    with pytest.raises(ValidationError):
        AppVmProfile.model_validate(PROFILE)


def test_a_service_profile_with_nothing_but_an_organisation() -> None:
    answer = ServiceVmProfile.model_validate({"org_id": "org-acme"})

    assert answer.extension_id is None and answer.request is None and answer.profile is None
    assert (answer.assigned.groups, answer.assigned.apps) == (0, 0)


@pytest.mark.parametrize(
    ("state", "flags"),
    [
        ("pending", (True, False, False)),
        ("approved", (False, True, False)),
        ("rejected", (False, False, True)),
    ],
)
def test_the_state_helpers_mirror_the_state(state: str, flags: tuple[bool, bool, bool]) -> None:
    parsed = VmProfileRequestRecord.model_validate(record(state=state))

    assert (parsed.is_pending, parsed.is_approved, parsed.is_rejected) == flags


@pytest.mark.parametrize("state", ["", "PENDING", "cancelled", None])
def test_a_state_igni_does_not_have_is_refused(state: object) -> None:
    with pytest.raises(ValidationError):
        VmProfileRequestRecord.model_validate(record(state=state))


def test_a_record_reads_its_times_and_who_decided() -> None:
    parsed = VmProfileRequestRecord.model_validate(
        record(
            state="rejected",
            decided_by={"kind": "user", "id": "u-ada", "acting_as": "org_admin"},
            decided_at="2026-01-03T00:00:00+00:00",
            reason="too much memory",
            profile_id=None,
        )
    )

    assert parsed.requested_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert parsed.decided_at == datetime(2026, 1, 3, tzinfo=UTC)
    assert parsed.decided_by is not None and parsed.decided_by.acting_as == "org_admin"
    assert parsed.reason == "too much memory"
    assert VmProfileRequestRecord.model_validate(record()).decided_by is None


@pytest.mark.parametrize(
    "changes",
    [
        {"requested_at": "yesterday"},
        {"decided_at": "soon"},
        {"subject": {"kind": "bot", "id": "x"}},
    ],
    ids=["requested-at", "decided-at", "subject-kind"],
)
def test_a_record_with_a_malformed_time_or_subject_is_refused(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        VmProfileRequestRecord.model_validate(record(**changes))


def test_a_refusal_carries_the_status_and_igni_s_detail() -> None:
    response = httpx.Response(422, json={"detail": "memory_mib is over the cap of 8192"})

    error = refusal(response)

    assert isinstance(error, VmProfileRefused)
    assert (error.status, error.detail) == (422, "memory_mib is over the cap of 8192")
    assert (
        str(error) == "igni refused the VM profile request: 422 memory_mib is over the cap of 8192"
    )


@pytest.mark.parametrize(
    ("response", "said"),
    [
        (httpx.Response(502, text="bad gateway"), "bad gateway"),
        (httpx.Response(400, json={"error": "x"}), '{"error":"x"}'),
        (httpx.Response(400, json=["a", "b"]), '["a","b"]'),
        (httpx.Response(400, json="plain"), '"plain"'),
        (httpx.Response(400, json={"detail": ["a", "b"]}), "['a', 'b']"),
        (httpx.Response(400, text=""), ""),
    ],
    ids=["not-json", "no-detail", "array", "string", "list-detail", "empty"],
)
def test_without_a_detail_the_refusal_says_the_body(response: httpx.Response, said: str) -> None:
    error = refusal(response)

    assert error.detail == said


class Tokens:
    """What igni answers a service-token request with; stands in for the token client."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.asked: list[tuple[str, str, str]] = []

    async def request(self, method: str, path: str, *, org_id: str) -> httpx.Response:
        self.asked.append((method, path, org_id))
        return self.response


def reader(response: httpx.Response) -> tuple[ServiceVmProfiles, Tokens]:
    tokens = Tokens(response)
    return ServiceVmProfiles(cast(ServiceTokens, tokens)), tokens


async def test_the_read_asks_for_the_organisation_and_parses_the_answer() -> None:
    profiles, tokens = reader(
        httpx.Response(
            200,
            json={
                "org_id": "org-acme",
                "extension_id": "acme.browser",
                "request": record(),
                "profile": PROFILE,
                "assigned": {"groups": 1, "apps": 2},
            },
        )
    )

    answer = await profiles.of("org-acme")

    assert tokens.asked == [("GET", IgniPaths.SERVICE_VM_PROFILE, "org-acme")]
    assert answer.extension_id == "acme.browser"
    assert answer.request is not None and answer.request.is_pending
    assert answer.profile is not None and answer.profile.profile_name == "Standard"
    assert (answer.assigned.groups, answer.assigned.apps) == (1, 2)


@pytest.mark.parametrize("status", [201, 204, 400, 401, 403, 404, 500, 503])
async def test_any_status_but_200_is_igni_being_unavailable(status: int) -> None:
    profiles, _ = reader(httpx.Response(status, json={"org_id": "org-acme"}))

    with pytest.raises(IgniUnavailable, match=f"answered the VM profile read {status}"):
        await profiles.of("org-acme")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, text=""),
        httpx.Response(200, json={}),
        httpx.Response(200, json=["org-acme"]),
        httpx.Response(200, json={"org_id": "o", "request": {"id": "r-1"}}),
        httpx.Response(200, json={"org_id": "o", "profile": {"profile_id": "p"}}),
    ],
    ids=["not-json", "empty", "no-org", "array", "partial-request", "partial-profile"],
)
async def test_an_answer_that_does_not_fit_is_igni_being_unavailable(
    response: httpx.Response,
) -> None:
    profiles, _ = reader(response)

    with pytest.raises(IgniUnavailable, match="with something else"):
        await profiles.of("org-acme")
