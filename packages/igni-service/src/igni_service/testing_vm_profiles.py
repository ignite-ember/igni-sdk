"""`FakeIgni`'s VM profiles: requests, an org admin's decisions, and what a VM gets.

What `FakeIgni.vm_profiles` keeps, with igni server's rules
(`docs/service-identity.md` §12):

* an **app** requests with its own token, for itself only; the same
  request again keeps its state, a changed one is `pending` again;
* an **extension**'s request is its uploaded manifest's `vm` section, one
  per organisation, appearing the first time anything asks;
* a request over the platform's caps is refused (400);
* nothing changes what a VM gets until a test, playing the org admin,
  calls `approve(org_id, VmProfileSubject.app(app_id))` (or
  `VmProfileSubject.extension(extension_id)`) — which makes the profile
  (or replaces the one an earlier approval made) and, for an app,
  assigns it — or `reject`.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from igni_service.testing_bundles import HeldExtension
from igni_service.testing_vm_rules import FakeCaps, FakeProfile, ManifestVm, Resolved
from igni_service.testing_wire import DetailError
from igni_service.vm_profiles import (
    AppVmProfile,
    Assigned,
    Decider,
    RequestedVmProfile,
    Requester,
    RequestState,
    RequestSubject,
    ServiceVmProfile,
    VmProfileRequest,
    VmProfileRequestRecord,
)


class NoVmProfileRequest(LookupError):
    """A test played the org admin on a request nobody has made yet."""

    def __init__(self, org_id: str, kind: str, subject_id: str) -> None:
        extension = (
            "An extension's request is its uploaded manifest's `vm` section, and appears the "
            "first time the service asks after it: upload the bundle (start the service with "
            "IGNI_EXTENSION_BUNDLE, or `await fake.upload(bundle, igni)`), then "
            f"`await igni.host({org_id!r}).extension_vm_profile()`."
        )
        app = "An app's appears once it asks: `await app.vm_profile.request(...)`."
        how = f"{extension} {app}" if kind == "extension" else f"{app} {extension}"
        super().__init__(f"no VM profile request from {kind} {subject_id} in {org_id}. {how}")


class VmProfileSubject(BaseModel):
    """Whose VM profile request: an app's, or an extension's."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    kind: Literal["app", "extension"]
    """`app` or `extension`."""
    subject_id: str
    """The app's id, or the extension's manifest id."""

    @classmethod
    def app(cls, app_id: str) -> VmProfileSubject:
        """An app's own request."""
        return cls(kind="app", subject_id=app_id)

    @classmethod
    def extension(cls, extension_id: str) -> VmProfileSubject:
        """An extension's request: its uploaded manifest's `vm` section."""
        return cls(kind="extension", subject_id=extension_id)


class FakeVmProfiles:
    """One deployment's VM profiles and the requests for them, per organisation."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        #: The wall clock a request's and a decision's time are read from;
        #: `FakeIgni` hands it its own, so a test can move it.
        self._clock = clock
        self.caps = FakeCaps()
        """The platform's caps every request is checked against; change them to play another
        platform.
        """
        self.requests: dict[tuple[str, str, str], VmProfileRequestRecord] = {}
        """Every request, by `(org_id, kind, subject_id)`."""
        self.profiles: dict[tuple[str, str], FakeProfile] = {}
        """Profiles approvals made, by `(org_id, profile_id)`."""
        self.app_profiles: dict[tuple[str, str], str] = {}
        """The profile each app has, by `(org_id, app_id)`; none: the default."""
        self.assigned: dict[tuple[str, str], Assigned] = {}
        """How many groups and apps a profile was given, by `(org_id, profile_id)`."""

    # ── Playing the org admin ───────────────────────────────────────

    def request(self, org_id: str, subject: VmProfileSubject) -> VmProfileRequestRecord:
        """The request `subject` made in `org_id`. `NoVmProfileRequest` if it made none."""
        try:
            return self.requests[(org_id, subject.kind, subject.subject_id)]
        except KeyError:
            raise NoVmProfileRequest(org_id, subject.kind, subject.subject_id) from None

    def approve(
        self, org_id: str, subject: VmProfileSubject, *, by: str = "u-admin"
    ) -> VmProfileRequestRecord:
        """Approve it, as an org admin: the profile is made or replaced, an app's assigned.

        The request must exist: an app's once it asked
        (`app.vm_profile.request`), an extension's once its bundle is
        uploaded and the service asked after it
        (`host.extension_vm_profile()`). `NoVmProfileRequest` (a
        `LookupError`) otherwise, saying so.
        """
        record = self.request(org_id, subject)
        profile_id = record.profile_id or str(uuid.uuid4())
        self.profiles[(org_id, profile_id)] = FakeProfile(
            id=profile_id,
            name=record.subject.name or subject.subject_id,
            settings=Resolved.model_validate(record.requested.model_dump()),
        )
        if subject.kind == "app":
            self.app_profiles[(org_id, subject.subject_id)] = profile_id
        return self._decide(record, "approved", by, profile_id=profile_id)

    def reject(
        self,
        org_id: str,
        subject: VmProfileSubject,
        *,
        reason: str | None = None,
        by: str = "u-admin",
    ) -> VmProfileRequestRecord:
        """Reject it, as an org admin: what the VM gets is untouched."""
        record = self.request(org_id, subject)
        return self._decide(record, "rejected", by, reason=reason)

    def assign(self, org_id: str, profile_id: str, *, groups: int = 0, apps: int = 0) -> None:
        """Say how many groups and apps an org admin gave a profile."""
        self.assigned[(org_id, profile_id)] = Assigned(groups=groups, apps=apps)

    def _decide(
        self,
        record: VmProfileRequestRecord,
        state: RequestState,
        by: str,
        *,
        profile_id: str | None = None,
        reason: str | None = None,
    ) -> VmProfileRequestRecord:
        decided = record.model_copy(
            update={
                "state": state,
                "decided_by": Decider(kind="person", id=by, acting_as="org_admin"),
                "decided_at": self._now(),
                "reason": reason,
                "profile_id": profile_id or record.profile_id,
            }
        )
        self.requests[(record.org_id, record.subject.kind, record.subject.id)] = decided
        return decided

    # ── The wire ────────────────────────────────────────────────────

    def app_put(self, org_id: str, app_id: str, name: str, body: bytes) -> httpx.Response:
        """Answer an app's `PUT` of its VM profile request as igni does. Called by the fake's
        router.
        """
        try:
            resolved = Resolved.of(VmProfileRequest.model_validate_json(body or b"{}"))
        except ValidationError as exc:
            return DetailError(detail=str(exc), status=422).to_response()
        over = self.caps.refusal(resolved)
        if over:
            return DetailError(detail=over).to_response()
        record, changed = self._file(
            org_id,
            RequestSubject(kind="app", id=app_id, name=name),
            resolved,
            requested_by=Requester(kind="app", id=app_id),
        )
        return httpx.Response(201 if changed else 200, json=record.model_dump(mode="json"))

    def app_get(self, org_id: str, app_id: str) -> httpx.Response:
        """Answer an app's `GET` of its request as igni does. Called by the fake's router."""
        record = self.requests.get((org_id, "app", app_id))
        if record is None:
            return DetailError(
                detail="This app has asked for no VM profile", status=404
            ).to_response()
        return httpx.Response(200, json=record.model_dump(mode="json"))

    def app_profile(self, org_id: str, app_id: str) -> httpx.Response:
        """Answer an app's `GET` of what its VM gets now as igni does. Called by the fake's router."""
        profile = self._profile(org_id, self.app_profiles.get((org_id, app_id)))
        served = AppVmProfile(
            **self.caps.serve(profile).model_dump(), volume_gib=profile.settings.volume_gib
        )
        return httpx.Response(200, json=served.model_dump(mode="json"))

    def service(self, org_id: str, client_id: str, shipped: HeldExtension | None) -> httpx.Response:
        """What `GET /v1/service-vm-profile` answers a service for one organisation."""
        vm = shipped.manifest.vm if shipped else None
        if shipped is None or vm is None:
            return httpx.Response(200, json=ServiceVmProfile(org_id=org_id).model_dump(mode="json"))
        extension_id = shipped.extension_id
        try:
            resolved = Resolved.of(ManifestVm.model_validate(vm))
        except ValidationError as exc:
            return DetailError(detail=str(exc), status=422).to_response()
        record, _ = self._file(
            org_id,
            RequestSubject(
                kind="extension", id=extension_id, name=shipped.manifest.name or extension_id
            ),
            resolved,
            requested_by=Requester(kind="service", id=client_id),
        )
        profile = self.profiles.get((org_id, record.profile_id)) if record.profile_id else None
        answer = ServiceVmProfile(
            org_id=org_id,
            extension_id=extension_id,
            request=record,
            profile=self.caps.serve(profile) if profile else None,
            assigned=self.assigned.get((org_id, profile.id), Assigned()) if profile else Assigned(),
        )
        return httpx.Response(200, json=answer.model_dump(mode="json"))

    # ── igni's rules ────────────────────────────────────────────────

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self._clock(), UTC)

    @staticmethod
    def _digest(value: object) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()[:32]

    def _file(
        self,
        org_id: str,
        subject: RequestSubject,
        resolved: Resolved,
        *,
        requested_by: Requester,
    ) -> tuple[VmProfileRequestRecord, bool]:
        """Store the request; whether it is new or changed (and so pending)."""
        key = (org_id, subject.kind, subject.id)
        version = self._digest(resolved.model_dump(mode="json"))
        held = self.requests.get(key)
        if held is not None and held.version == version:
            return held, False
        record = VmProfileRequestRecord(
            id=held.id if held else str(uuid.uuid4()),
            org_id=org_id,
            subject=subject,
            state="pending",
            requested=RequestedVmProfile.model_validate(resolved.model_dump()),
            version=version,
            packages_version=self._digest(
                resolved.model_dump(mode="json", include={"packages", "setup_script"})
            ),
            within_caps=self.caps.refusal(resolved) is None,
            requested_by=requested_by,
            requested_at=self._now(),
            profile_id=held.profile_id if held else None,
        )
        self.requests[key] = record
        return record, True

    def _profile(self, org_id: str, profile_id: str | None) -> FakeProfile:
        found = self.profiles.get((org_id, profile_id)) if profile_id else None
        return found or FakeProfile.default(org_id)


__all__ = ["FakeVmProfiles", "NoVmProfileRequest", "VmProfileSubject"]
