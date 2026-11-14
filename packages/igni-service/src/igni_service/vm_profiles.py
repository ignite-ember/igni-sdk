"""What a producer's VM needs in igni's cloud, asked for — and what it gets.

In igni's cloud every producer runs in a microVM of its own, built from a
**VM profile**: its memory and vCPUs, how long it idles before a pause,
its volume, and the packages and setup script baked into its read-only
layer. An org admin defines profiles and gives one to each group and app
(igni server's `docs/service-identity.md` §12).

Packages and the setup script run **as root** when that layer is built, so
nothing gets into a VM that an org admin has not approved. An app or an
extension that needs something — a headless browser, a native library,
more memory — **requests** it:

* an **app**, as itself (`app.vm_profile.request` on an `igni_service.app.IgniApp`);
* an **extension**, in its manifest's `vm` section — and the service that
  ships it reads what became of that in each organisation
  (`Host.extension_vm_profile`).

igni keeps the request **pending** and shows the org admin exactly what
would run. Only their approval makes it a profile (an app's is assigned
to the app at once; an extension's the admin gives to the groups and apps
that use it). A changed request is pending again; the profile already
running is untouched until then. Nothing in this SDK can approve: that
takes an org admin's portal session, which no service or app holds.
"""

from __future__ import annotations

import contextlib
from datetime import datetime
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from igni_service.errors import IgniUnavailable, VmProfileRefused
from igni_service.service_tokens import ServiceTokens
from igni_service.urls import IgniPaths

PackageName = Annotated[
    str,
    StringConstraints(
        pattern=r"^[A-Za-z0-9@][A-Za-z0-9@/._+:=<>~^*!,-]{0,199}$", strip_whitespace=True
    ),
]
"""One package as its manager names it — `chromium`, `requests==2.32.3`,
`@playwright/mcp@0.0.41` — and nothing a shell would read as more than
one word. igni server's own rule, mirrored so a mistake is caught here.
"""

MAX_PACKAGES = 200
"""At most this many packages per manager."""
MAX_SETUP_SCRIPT = 65536
"""The longest setup script, in characters."""

RequestState = Literal["pending", "approved", "rejected"]


class VmPackages(BaseModel):
    """What the profile's read-only layer is built with, per package manager."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    apt: list[PackageName] = Field(default_factory=list, max_length=MAX_PACKAGES)
    """Debian packages, as `apt-get install` names them: `chromium`."""
    pip: list[PackageName] = Field(default_factory=list, max_length=MAX_PACKAGES)
    """Python packages, as `pip install` names them: `requests==2.32.3`."""
    npm: list[PackageName] = Field(default_factory=list, max_length=MAX_PACKAGES)
    """npm packages, installed globally: `@playwright/mcp@0.0.41`."""


class VmProfileRequest(BaseModel):
    """What an app asks its VM to have. Every field is optional.

    A field left out takes the deployment's Standard value, decided by igni
    server — only the fields set are sent (`body`). A nullable field set to
    `None` asks for that explicitly: `idle_before_pause_s=None` is never
    pausing, which the platform's caps may refuse.
    """

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    memory_mib: int | None = Field(default=None, ge=128, le=1_048_576)
    """The most memory the VM may have, in MiB: its size at boot."""
    normal_memory_mib: int | None = Field(default=None, ge=128, le=1_048_576)
    """What it normally has, in MiB; the node lends the rest while it needs it."""
    expected_memory_mib: int | None = Field(default=None, ge=128, le=1_048_576)
    """What the node expects it to use, for placing it; `None`: the node's rule."""
    vcpus: int | None = Field(default=None, ge=1, le=256)
    """Virtual CPUs (1-256)."""
    idle_before_pause_s: int | None = Field(default=None, ge=0)
    """Seconds idle before the VM is paused; `None` is never."""
    packages: VmPackages | None = None
    """What the profile's read-only layer is built with."""
    setup_script: str | None = Field(default=None, max_length=MAX_SETUP_SCRIPT)
    """Run as root when the profile's layer is built, after the packages."""
    volume_gib: int | None = Field(default=None, ge=1)
    """A new VM's volume, and how far an admin may grow it, in GiB."""
    volume_max_gib: int | None = Field(default=None, ge=1)
    """The largest an admin may grow the volume to, in GiB."""
    erase_after_idle_days: int | None = Field(default=None, ge=1, le=3650)
    """Days unwoken after which the app's VM is erased; `None` is never."""
    internet: bool | None = None
    """Whether the VM may reach the internet. Left out (or False): internal
    only — igni and the deployment's own allowed addresses. True asks the
    org admin for internet egress, a security grant they see as such;
    a node that is air-gapped, or not allowed to grant internet, still
    starts the VM internal-only.
    """

    def body(self) -> dict[str, object]:
        """The JSON igni is sent: only what was set."""
        return self.model_dump(mode="json", exclude_unset=True)


class RequestedVmProfile(BaseModel):
    """A request as igni resolved it: every value, the Standard ones filled in — what would run."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    memory_mib: int
    """The most memory the VM may have, in MiB."""
    normal_memory_mib: int
    """What it normally has, in MiB."""
    expected_memory_mib: int | None = None
    """What the node expects it to use; `None`: the node's rule."""
    vcpus: int
    """Virtual CPUs."""
    idle_before_pause_s: int | None = None
    """Seconds idle before the VM is paused; `None` is never."""
    packages: VmPackages = Field(default_factory=VmPackages)
    """What the profile's layer is built with."""
    setup_script: str | None = None
    """Run as root when the layer is built, after the packages."""
    volume_gib: int
    """A new VM's volume, in GiB."""
    volume_max_gib: int
    """The largest an admin may grow the volume to, in GiB."""
    erase_after_idle_days: int | None = None
    """Days unwoken after which the VM is erased; `None` is never."""
    internet: bool = False
    """Internet egress asked for; False is internal only."""


class RequestSubject(BaseModel):
    """Whose request it is: an app, or an extension."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    kind: Literal["app", "extension"]
    """`app` or `extension`."""
    id: str
    """The app's id, or the extension's manifest id."""
    name: str = ""
    """Its display name."""


class Requester(BaseModel):
    """Who sent the request: an app, or a service for its extension."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    kind: str
    """`app` or `service`."""
    id: str
    """The app's id, or the service's client id."""


class Decider(BaseModel):
    """The admin who approved or rejected it."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    kind: str
    """What decided: a `user`."""
    id: str
    """The admin's user id."""
    acting_as: str
    """`org_admin` or `super_admin`."""


class VmProfileRequestRecord(BaseModel):
    """One request, and what became of it."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    id: str
    """The request's id."""
    org_id: str
    """The organisation it was made in."""
    subject: RequestSubject
    """Whose request it is: an app, or an extension."""
    state: RequestState
    """`pending`, `approved` or `rejected`."""
    requested: RequestedVmProfile
    """What it asks for, with igni's Standard values filled in."""
    version: str
    """Changes whenever anything requested does; an approval names it."""
    packages_version: str
    """Changes whenever the packages or the setup script do: the layer Fleet builds."""
    within_caps: bool
    """False when it asks for more than the platform's caps allow now."""
    requested_by: Requester
    """Who sent it."""
    requested_at: datetime
    """When it was last sent (or changed)."""
    decided_by: Decider | None = None
    """The admin who approved or rejected it; `None` while pending."""
    decided_at: datetime | None = None
    """When they did."""
    reason: str | None = None
    """Why it was rejected, when the admin said."""
    profile_id: str | None = None
    """The profile an approval made, holding what was last approved."""

    @property
    def is_pending(self) -> bool:
        """Whether an org admin has yet to decide (`state == "pending"`)."""
        return self.state == "pending"

    @property
    def is_approved(self) -> bool:
        """Whether an org admin approved it (`state == "approved"`)."""
        return self.state == "approved"

    @property
    def is_rejected(self) -> bool:
        """Whether an org admin rejected it (`state == "rejected"`); `reason` may say why."""
        return self.state == "rejected"


class EffectiveVmProfile(BaseModel):
    """What a VM gets from a profile: its values, clamped to the platform's caps."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    profile_id: str
    """The profile's id."""
    profile_name: str
    """Its name, as the portal shows it."""
    memory_mib: int
    """The most memory the VM may have, in MiB."""
    normal_memory_mib: int
    """What it normally has, in MiB."""
    expected_memory_mib: int | None = None
    """What the node expects it to use; `None`: the node's rule."""
    vcpus: int
    """Virtual CPUs."""
    idle_before_pause_s: int | None = None
    """Seconds idle before the VM is paused; `None` is never."""
    packages: VmPackages = Field(default_factory=VmPackages)
    """What its read-only layer is built with."""
    setup_script: str | None = None
    """Run as root when the layer is built."""
    volume_max_gib: int
    """The largest an admin may grow a volume to, in GiB."""
    erase_after_idle_days: int | None = None
    """Days unwoken after which a VM is erased; `None` is never."""
    internet: bool = False
    """Whether the VM may reach the internet (where its node may grant it);
    False, and absent from an older igni server: internal only.
    """


class AppVmProfile(EffectiveVmProfile):
    """What the app's own VM gets now, with its volume."""

    volume_gib: int
    """The app's volume, in GiB: the profile's, or more where an admin grew it."""


class Assigned(BaseModel):
    """How many of the organisation's groups and apps have a profile."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    groups: int = 0
    """How many groups were given the profile."""
    apps: int = 0
    """How many apps were given the profile."""


class ServiceVmProfile(BaseModel):
    """A service's extension's request in one organisation, and the profile it became."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    org_id: str
    """The organisation asked about."""
    extension_id: str | None = None
    """`None` when this service ships no extension, or its manifest has no `vm`."""
    request: VmProfileRequestRecord | None = None
    """The extension's request there; `None` when none was made."""
    profile: EffectiveVmProfile | None = None
    """What the approval made, clamped to the caps; `None` until approved."""
    assigned: Assigned = Field(default_factory=Assigned)
    """Who the org admin gave that profile to."""


def refusal(response: httpx.Response) -> VmProfileRefused:
    """igni's own words for a refusal: its `detail`, or the body.

    Args:
        response: igni's refusing answer.
    """
    detail: object = response.text
    with contextlib.suppress(ValueError, AttributeError):
        detail = response.json().get("detail", detail)
    return VmProfileRefused(response.status_code, str(detail))


class ServiceVmProfiles:
    """`GET /v1/service-vm-profile`, with this service's token for one organisation.

    Args:
        tokens: The service's token client, which signs each read.
    """

    def __init__(self, tokens: ServiceTokens) -> None:
        self._tokens = tokens

    async def of(self, org_id: str) -> ServiceVmProfile:
        """The VM profile this service has in one organisation.

        Args:
            org_id: The organisation to read it in.

        Raises `IgniUnavailable`.
        """
        response = await self._tokens.request("GET", IgniPaths.SERVICE_VM_PROFILE, org_id=org_id)
        if response.status_code != 200:
            raise IgniUnavailable(f"igni answered the VM profile read {response.status_code}")
        try:
            return ServiceVmProfile.model_validate(response.json())
        except (ValidationError, ValueError) as exc:
            raise IgniUnavailable("igni answered the VM profile read with something else") from exc
