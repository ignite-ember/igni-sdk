"""igni's rules for a VM profile as the fake applies them: Standard, the checks, the caps, the answers.

`Resolved`, `ManifestVm`, `FakeProfile` and `FakeCaps` decide what a
request means, what the platform refuses and what a VM gets; `FakeVmProfiles`
turns that into igni's answers. These read the rules at their edges and the
answers' bodies directly, beside `test_vm_profiles.py`'s walk through the
SDK.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from igni_service import VmPackages, VmProfileRequest
from igni_service.testing import FakeCaps, FakeVmProfiles, VmProfileSubject
from igni_service.testing_bundles import HeldExtension, UploadedManifest
from igni_service.testing_vm_rules import FakeProfile, ManifestVm, Resolved
from igni_service.vm_profiles import (
    AppVmProfile,
    ServiceVmProfile,
    VmProfileRequestRecord,
)

from .conftest import ORG, OTHER_ORG


def resolved(**changes: object) -> Resolved:
    return Resolved.of(VmProfileRequest.model_validate(changes))


class TestStandard:
    def test_it_is_the_profile_igni_ships(self) -> None:
        assert Resolved.standard().model_dump() == {
            "memory_mib": 4096,
            "normal_memory_mib": 1024,
            "expected_memory_mib": None,
            "vcpus": 1,
            "idle_before_pause_s": 10,
            "packages": VmPackages().model_dump(),
            "setup_script": None,
            "volume_gib": 10,
            "volume_max_gib": 50,
            "erase_after_idle_days": None,
            "internet": False,
        }

    def test_a_request_overlays_only_the_fields_it_set(self) -> None:
        got = resolved(vcpus=3, setup_script=None)

        assert got.vcpus == 3 and got.setup_script is None
        assert got.memory_mib == 4096 and got.idle_before_pause_s == 10

    def test_a_field_set_to_none_is_asked_for_and_a_field_left_out_is_not(self) -> None:
        assert resolved(idle_before_pause_s=None).idle_before_pause_s is None
        assert resolved().idle_before_pause_s == 10

    def test_the_default_profile_is_standard_named_for_its_organisation(self) -> None:
        default = FakeProfile.default("org-7")

        assert (default.id, default.name) == ("default-org-7", "Standard")
        assert default.settings == Resolved.standard()


class TestWhatIsMalformed:
    def test_normal_memory_may_not_exceed_memory(self) -> None:
        with pytest.raises(ValidationError, match="normal_memory_mib may not exceed memory_mib"):
            resolved(memory_mib=512, normal_memory_mib=513)

    def test_expected_memory_may_not_exceed_memory(self) -> None:
        with pytest.raises(ValidationError, match="expected_memory_mib may not exceed memory_mib"):
            resolved(memory_mib=2048, expected_memory_mib=2049)

    def test_volume_may_not_exceed_its_maximum(self) -> None:
        with pytest.raises(ValidationError, match="volume_gib may not exceed volume_max_gib"):
            resolved(volume_gib=60)

    def test_what_fits_exactly_is_accepted(self) -> None:
        got = resolved(
            memory_mib=2048, normal_memory_mib=2048, expected_memory_mib=2048, volume_gib=50
        )

        assert got.normal_memory_mib == got.expected_memory_mib == 2048 and got.volume_gib == 50

    def test_a_standard_value_that_the_request_makes_inconsistent_is_caught_too(self) -> None:
        # Standard's normal memory is 1024: a smaller ceiling alone breaks it.
        with pytest.raises(ValidationError, match="normal_memory_mib may not exceed"):
            resolved(memory_mib=512)

    def test_a_manifest_reads_camel_case_or_snake_case_and_ignores_what_it_does_not_know(
        self,
    ) -> None:
        camel = ManifestVm.model_validate({"volumeMaxGib": 80, "unknownKey": {"a": 1}})
        snake = ManifestVm.model_validate({"volume_max_gib": 80})

        assert camel.volume_max_gib == snake.volume_max_gib == 80
        assert "unknownKey" not in camel.model_dump()

    def test_a_request_itself_forbids_what_it_does_not_know(self) -> None:
        with pytest.raises(ValidationError):
            VmProfileRequest.model_validate({"unknownKey": 1})


class TestTheCaps:
    def test_they_are_igni_server_s_defaults(self) -> None:
        caps = FakeCaps()

        assert (
            caps.max_memory_mib,
            caps.max_vcpus,
            caps.max_idle_before_pause_s,
            caps.max_volume_gib,
        ) == (8192, 4, 3600, 200)

    def test_a_request_within_them_is_not_refused(self) -> None:
        assert FakeCaps().refusal(Resolved.standard()) is None

    def test_what_sits_exactly_on_each_cap_passes_and_one_over_is_refused_in_igni_s_words(
        self,
    ) -> None:
        caps = FakeCaps()
        edge = resolved(
            memory_mib=8192, vcpus=4, idle_before_pause_s=3600, volume_gib=10, volume_max_gib=200
        )
        assert caps.refusal(edge) is None

        assert caps.refusal(resolved(memory_mib=8193)) == (
            "The memory ceiling may be at most 8192 MiB on this platform"
        )
        assert caps.refusal(resolved(vcpus=5)) == "At most 4 vCPUs on this platform"
        assert caps.refusal(resolved(idle_before_pause_s=3601)) == (
            "A VM may stay awake idle for at most 3600 seconds on this platform"
        )
        assert caps.refusal(resolved(volume_max_gib=201)) == (
            "A volume may grow to at most 200 GiB on this platform"
        )

    def test_never_pausing_is_refused_while_there_is_a_cap_and_allowed_without_one(self) -> None:
        never = resolved(idle_before_pause_s=None)

        assert FakeCaps().refusal(never) == (
            "A VM may stay awake idle for at most 3600 seconds on this platform"
        )
        assert FakeCaps(max_idle_before_pause_s=None).refusal(never) is None

    def test_the_first_cap_broken_is_the_one_named(self) -> None:
        caps = FakeCaps(max_memory_mib=1024, max_vcpus=1)

        assert "memory ceiling" in (caps.refusal(resolved(memory_mib=2048, vcpus=2)) or "")

    def test_what_a_vm_gets_is_within_the_caps_and_a_cap_lowered_later_still_clamps(self) -> None:
        profile = FakeProfile(id="p", name="Big", settings=resolved(vcpus=4, volume_max_gib=200))
        assert FakeCaps().serve(profile).vcpus == 4

        lowered = FakeCaps(max_vcpus=2, max_volume_gib=100).serve(profile)

        assert lowered.vcpus == 2 and lowered.volume_max_gib == 100
        assert (lowered.profile_id, lowered.profile_name) == ("p", "Big")

    def test_an_unset_expected_memory_stays_unset(self) -> None:
        served = FakeCaps().serve(FakeProfile(id="p", name="n", settings=Resolved.standard()))

        assert served.expected_memory_mib is None

    def test_with_no_idle_cap_the_idle_time_is_served_as_it_is_and_never_stays_never(self) -> None:
        caps = FakeCaps(max_idle_before_pause_s=None)

        never = caps.serve(
            FakeProfile(id="p", name="n", settings=resolved(idle_before_pause_s=None))
        )
        some = caps.serve(FakeProfile(id="p", name="n", settings=resolved(idle_before_pause_s=99)))

        assert never.idle_before_pause_s is None and some.idle_before_pause_s == 99

    def test_the_packages_it_serves_are_a_copy_of_the_profile_s(self) -> None:
        profile = FakeProfile(
            id="p",
            name="n",
            settings=resolved(packages=VmPackages(apt=["git"]), setup_script="true\n"),
        )

        served = FakeCaps().serve(profile)
        served.packages.apt.append("curl")

        assert profile.settings.packages.apt == ["git"]
        assert served.setup_script == "true\n"


def held(vm: dict[str, object] | None, *, name: str | None = "Browser") -> HeldExtension:
    return HeldExtension(
        client_id="client-1",
        extension_id="acme.browser",
        version="1",
        sha256="0" * 64,
        archive=b"",
        manifest=UploadedManifest(id="acme.browser", version="1", name=name, vm=vm),
    )


class TestTheAnswersOnTheWire:
    def test_an_app_that_never_asked_is_told_so_in_a_404(self) -> None:
        answer = FakeVmProfiles().app_get(ORG, "app-1")

        assert answer.status_code == 404
        assert answer.json() == {"detail": "This app has asked for no VM profile"}

    def test_the_request_an_app_made_is_read_back_whole_and_only_in_its_own_organisation(
        self,
    ) -> None:
        profiles = FakeVmProfiles()
        profiles.app_put(ORG, "app-1", "Bot", b'{"vcpus": 2}')

        mine = profiles.app_get(ORG, "app-1")
        theirs = profiles.app_get(OTHER_ORG, "app-1")

        assert mine.status_code == 200
        record = VmProfileRequestRecord.model_validate(mine.json())
        assert record.requested.vcpus == 2 and record.subject.name == "Bot"
        assert theirs.status_code == 404

    def test_a_stored_request_says_whether_it_is_within_the_caps_and_versions_its_packages(
        self,
    ) -> None:
        profiles = FakeVmProfiles()
        first = VmProfileRequestRecord.model_validate(
            profiles.app_put(ORG, "a", "A", b'{"packages": {"apt": ["git"]}}').json()
        )
        other_packages = VmProfileRequestRecord.model_validate(
            profiles.app_put(ORG, "b", "B", b'{"packages": {"apt": ["curl"]}}').json()
        )
        other_cpus = VmProfileRequestRecord.model_validate(
            profiles.app_put(ORG, "c", "C", b'{"packages": {"apt": ["git"]}, "vcpus": 2}').json()
        )

        other_script = VmProfileRequestRecord.model_validate(
            profiles.app_put(
                ORG, "d", "D", b'{"packages": {"apt": ["git"]}, "setup_script": "true"}'
            ).json()
        )

        assert first.within_caps
        assert first.packages_version != other_script.packages_version
        assert first.packages_version != other_packages.packages_version
        # Packages and the setup script alone make that version; vcpus does not.
        assert first.packages_version == other_cpus.packages_version
        assert first.version != other_cpus.version

    @pytest.mark.parametrize(
        "body",
        [b"not json", b'{"vcpus": "two"}', b'{"vcpus": 0}', b'{"surprise": 1}', b"[]", b"null"],
    )
    def test_a_body_igni_cannot_read_is_a_422_and_stores_nothing(self, body: bytes) -> None:
        profiles = FakeVmProfiles()

        answer = profiles.app_put(ORG, "app-1", "Bot", body)

        assert answer.status_code == 422
        assert answer.json()["detail"]
        assert profiles.requests == {}

    def test_an_empty_body_asks_for_the_standard_profile(self) -> None:
        answer = FakeVmProfiles().app_put(ORG, "app-1", "Bot", b"")

        assert answer.status_code == 201
        requested = VmProfileRequestRecord.model_validate(answer.json()).requested
        assert requested.model_dump() == Resolved.standard().model_dump()

    def test_a_request_over_a_cap_is_a_400_in_igni_s_words_and_stores_nothing(self) -> None:
        profiles = FakeVmProfiles()

        answer = profiles.app_put(ORG, "app-1", "Bot", b'{"vcpus": 9}')

        assert answer.status_code == 400
        assert answer.json() == {"detail": "At most 4 vCPUs on this platform"}
        assert profiles.requests == {}

    def test_what_an_app_s_vm_gets_is_the_standard_profile_until_it_is_approved(self) -> None:
        profiles = FakeVmProfiles()
        profiles.app_put(ORG, "app-1", "Bot", b'{"vcpus": 2, "volume_gib": 20}')

        before = AppVmProfile.model_validate(profiles.app_profile(ORG, "app-1").json())
        profiles.approve(ORG, VmProfileSubject.app("app-1"))
        after = AppVmProfile.model_validate(profiles.app_profile(ORG, "app-1").json())

        assert (before.profile_name, before.vcpus, before.volume_gib) == ("Standard", 1, 10)
        assert before.profile_id == f"default-{ORG}"
        assert (after.profile_name, after.vcpus, after.volume_gib) == ("Bot", 2, 20)

    def test_a_profile_is_clamped_to_the_caps_as_they_are_when_it_is_read(self) -> None:
        profiles = FakeVmProfiles()
        profiles.app_put(ORG, "app-1", "Bot", b'{"vcpus": 4}')
        profiles.approve(ORG, VmProfileSubject.app("app-1"))

        profiles.caps = FakeCaps(max_vcpus=2)
        served = AppVmProfile.model_validate(profiles.app_profile(ORG, "app-1").json())

        assert served.vcpus == 2

    def test_a_service_that_shipped_no_bundle_or_no_vm_section_has_an_empty_answer(self) -> None:
        profiles = FakeVmProfiles()

        for shipped in (None, held(None)):
            answer = ServiceVmProfile.model_validate(
                profiles.service(ORG, "client-1", shipped).json()
            )
            assert answer == ServiceVmProfile(org_id=ORG)
        assert profiles.requests == {}

    def test_a_manifest_vm_igni_cannot_read_is_a_422(self) -> None:
        profiles = FakeVmProfiles()

        unreadable: list[dict[str, object]] = [
            {"vcpus": "many"},
            {"memoryMib": 512, "normalMemoryMib": 600},
        ]
        for vm in unreadable:
            answer = profiles.service(ORG, "client-1", held(vm))
            assert answer.status_code == 422, vm
            assert answer.json()["detail"]
        assert profiles.requests == {}

    def test_the_extension_s_request_is_filed_once_per_organisation_and_named_as_its_manifest(
        self,
    ) -> None:
        profiles = FakeVmProfiles()
        extension = held({"vcpus": 2})

        one = ServiceVmProfile.model_validate(profiles.service(ORG, "client-1", extension).json())
        again = ServiceVmProfile.model_validate(profiles.service(ORG, "client-1", extension).json())
        elsewhere = ServiceVmProfile.model_validate(
            profiles.service(OTHER_ORG, "client-1", extension).json()
        )

        assert one.request is not None and again.request is not None
        assert one.request.id == again.request.id
        assert elsewhere.request is not None and elsewhere.request.id != one.request.id
        assert one.request.subject.name == "Browser"
        assert one.request.requested_by is not None and one.request.requested_by.kind == "service"
        assert one.profile is None and one.assigned.groups == one.assigned.apps == 0
        assert len(profiles.requests) == 2

    def test_a_manifest_with_no_name_is_named_by_its_id(self) -> None:
        answer = ServiceVmProfile.model_validate(
            FakeVmProfiles().service(ORG, "client-1", held({}, name=None)).json()
        )

        assert answer.request is not None and answer.request.subject.name == "acme.browser"

    def test_what_an_admin_assigned_reaches_the_answer_beside_the_clamped_profile(self) -> None:
        profiles = FakeVmProfiles()
        extension = held({"vcpus": 4})
        profiles.service(ORG, "client-1", extension)
        approved = profiles.approve(ORG, VmProfileSubject.extension("acme.browser"))
        assert approved.profile_id is not None
        profiles.assign(ORG, approved.profile_id, groups=3, apps=5)
        profiles.caps = FakeCaps(max_vcpus=2)

        answer = ServiceVmProfile.model_validate(
            profiles.service(ORG, "client-1", extension).json()
        )

        assert (answer.assigned.groups, answer.assigned.apps) == (3, 5)
        assert answer.profile is not None and answer.profile.vcpus == 2
        assert answer.request is not None and answer.request.is_approved
        # Another organisation's admin assigned nothing.
        other = ServiceVmProfile.model_validate(
            profiles.service(OTHER_ORG, "client-1", extension).json()
        )
        assert other.assigned.groups == 0 and other.profile is None


class TestADecisionOnADecision:
    def test_approving_a_rejected_request_makes_it_approved_and_forgets_the_reason(self) -> None:
        profiles = FakeVmProfiles()
        profiles.app_put(ORG, "app-1", "Bot", b"{}")
        subject = VmProfileSubject.app("app-1")

        rejected = profiles.reject(ORG, subject, reason="too big")
        approved = profiles.approve(ORG, subject, by="u-ada")

        assert rejected.reason == "too big"
        assert approved.is_approved and approved.reason is None
        assert approved.decided_by is not None and approved.decided_by.id == "u-ada"
        assert profiles.request(ORG, subject) == approved

    def test_rejecting_an_approved_request_leaves_the_profile_it_made_in_place(self) -> None:
        profiles = FakeVmProfiles()
        profiles.app_put(ORG, "app-1", "Bot", b'{"vcpus": 2}')
        subject = VmProfileSubject.app("app-1")
        approved = profiles.approve(ORG, subject)

        rejected = profiles.reject(ORG, subject, reason="changed my mind")

        assert rejected.profile_id == approved.profile_id
        served = AppVmProfile.model_validate(profiles.app_profile(ORG, "app-1").json())
        assert served.vcpus == 2

    def test_the_subject_is_a_model_with_a_kind_and_an_id(self) -> None:
        assert json.loads(VmProfileSubject.app("a").model_dump_json()) == {
            "kind": "app",
            "subject_id": "a",
        }
        assert VmProfileSubject.extension("e").kind == "extension"
