"""igni server's rules for a VM profile, as `FakeVmProfiles` applies them.

`Resolved` is a request with the deployment's Standard values filled in,
checked as igni checks a profile; `ManifestVm` is an extension manifest's
`vm` section, the same request in the manifest's camelCase; `FakeCaps` are
the platform's caps, which refuse a request over them and clamp what a VM
gets (`docs/service-identity.md` §12).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.alias_generators import to_camel

from igni_service.vm_profiles import EffectiveVmProfile, RequestedVmProfile, VmProfileRequest


class ManifestVm(VmProfileRequest):
    """An extension manifest's `vm` section: a request, spelt in camelCase as the rest of it.

    Keys igni does not read are ignored, as igni ignores them.
    """

    model_config = ConfigDict(extra="ignore", alias_generator=to_camel, populate_by_name=True)


class Resolved(RequestedVmProfile):
    """A request with the Standard values filled in, checked as igni checks a profile."""

    @classmethod
    def standard(cls) -> Resolved:
        """The deployment's Standard profile, as igni server ships it."""
        return cls(
            memory_mib=4096,
            normal_memory_mib=1024,
            vcpus=1,
            idle_before_pause_s=10,
            volume_gib=10,
            volume_max_gib=50,
        )

    @classmethod
    def of(cls, request: VmProfileRequest) -> Resolved:
        """`request`'s values over the Standard ones. Raises `ValidationError`.

        Args:
            request: The profile asked for; only the values it sets are
                used, the Standard ones fill in the rest.
        """
        return cls.model_validate(
            {**cls.standard().model_dump(), **request.model_dump(exclude_unset=True)}
        )

    @model_validator(mode="after")
    def _fits(self) -> Resolved:
        if self.normal_memory_mib > self.memory_mib:
            raise ValueError("normal_memory_mib may not exceed memory_mib")
        if self.expected_memory_mib is not None and self.expected_memory_mib > self.memory_mib:
            raise ValueError("expected_memory_mib may not exceed memory_mib")
        if self.volume_gib > self.volume_max_gib:
            raise ValueError("volume_gib may not exceed volume_max_gib")
        return self


class FakeProfile(BaseModel):
    """A profile an approval made, or the organisation's Standard default."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    id: str
    """The profile's id."""
    name: str
    """Its name."""
    settings: Resolved
    """What a VM it is given gets, every value filled in."""

    @classmethod
    def default(cls, org_id: str) -> FakeProfile:
        """What a VM with no profile of its own gets.

        Args:
            org_id: The organisation the default profile is for; the
                profile's id is ``default-`` and that organisation's id.
        """
        return cls(id=f"default-{org_id}", name="Standard", settings=Resolved.standard())


class FakeCaps(BaseModel):
    """The platform's caps; igni server's defaults."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    max_memory_mib: int = 8192
    """The most memory a VM may have, in MiB."""
    max_vcpus: int = 4
    """The most virtual CPUs."""
    max_idle_before_pause_s: int | None = 3600
    """The longest a VM may stay idle before it is paused; `None` allows never pausing."""
    max_volume_gib: int = 200
    """The largest volume, in GiB."""

    def refusal(self, wanted: Resolved) -> str | None:
        """Why igni refuses `wanted` on this platform; `None` when it fits.

        Args:
            wanted: The profile to check: the request with the
                deployment's Standard values filled in.
        """
        if wanted.memory_mib > self.max_memory_mib:
            return f"The memory ceiling may be at most {self.max_memory_mib} MiB on this platform"
        if wanted.vcpus > self.max_vcpus:
            return f"At most {self.max_vcpus} vCPUs on this platform"
        longest = self.max_idle_before_pause_s
        if longest is not None and (
            wanted.idle_before_pause_s is None or wanted.idle_before_pause_s > longest
        ):
            return f"A VM may stay awake idle for at most {longest} seconds on this platform"
        if wanted.volume_max_gib > self.max_volume_gib:
            return f"A volume may grow to at most {self.max_volume_gib} GiB on this platform"
        return None

    def serve(self, profile: FakeProfile) -> EffectiveVmProfile:
        """What a VM gets from `profile`: its values, clamped to these caps.

        Args:
            profile: The profile a VM is given: an approval's, or the
                organisation's Standard default.
        """
        s = profile.settings
        memory = min(s.memory_mib, self.max_memory_mib)
        idle = s.idle_before_pause_s
        if self.max_idle_before_pause_s is not None:
            idle = (
                self.max_idle_before_pause_s
                if idle is None
                else min(idle, self.max_idle_before_pause_s)
            )
        return EffectiveVmProfile(
            profile_id=profile.id,
            profile_name=profile.name,
            memory_mib=memory,
            normal_memory_mib=min(s.normal_memory_mib, memory),
            expected_memory_mib=None
            if s.expected_memory_mib is None
            else min(s.expected_memory_mib, memory),
            vcpus=min(s.vcpus, self.max_vcpus),
            idle_before_pause_s=idle,
            packages=s.packages.model_copy(deep=True),
            setup_script=s.setup_script,
            volume_max_gib=min(s.volume_max_gib, self.max_volume_gib),
            erase_after_idle_days=s.erase_after_idle_days,
            internet=s.internet,
        )


__all__ = ["FakeCaps", "FakeProfile", "ManifestVm", "Resolved"]
