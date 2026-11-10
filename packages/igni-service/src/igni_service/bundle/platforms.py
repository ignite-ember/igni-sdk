"""The platforms igni runs on, as uv and pip name them.

CPython 3.12 on macOS 26 and later on arm64, Linux x86_64 and Windows
x86_64. A wheelhouse is filled for each of them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from igni_service.assets import AssetPlatform

PYTHON_VERSION = "3.12"

MACOS_TARGET = "26.0"
"""The oldest macOS a bundle installs on. Every customer runs 26 or 27;
a wheel built for an older macOS still installs there, so this only
stops the resolver choosing an old release for an old system.
"""


class Platform(BaseModel):
    """One platform igni runs on, as uv and pip name it."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    name: str
    asset: AssetPlatform
    """The manifest's name for it, in `assets[].platform`."""
    uv: str
    """`uv pip compile --python-platform`."""
    pip: tuple[str, ...]
    """`pip download --platform`, each one; pip does not widen a
    `manylinux_2_x` tag to the older ones on its own. It does widen a
    `macosx_26_0_arm64` one, to every older macOS and `universal2`.
    """
    uv_env: tuple[tuple[str, str], ...] = ()
    """Set for `uv pip compile`: uv reads the macOS it resolves for from
    `MACOSX_DEPLOYMENT_TARGET`, and assumes 13 without it.
    """

    def pip_flags(self) -> list[str]:
        return [flag for tag in self.pip for flag in ("--platform", tag)]


PLATFORMS: tuple[Platform, ...] = (
    Platform(
        name="macOS arm64",
        asset=AssetPlatform.MACOS_ARM64,
        uv="aarch64-apple-darwin",
        pip=(f"macosx_{MACOS_TARGET.replace('.', '_')}_arm64",),
        uv_env=(("MACOSX_DEPLOYMENT_TARGET", MACOS_TARGET),),
    ),
    Platform(
        name="Linux x86_64",
        asset=AssetPlatform.LINUX_X86_64,
        uv="x86_64-manylinux_2_28",
        pip=tuple(f"manylinux_2_{minor}_x86_64" for minor in range(28, 16, -1))
        + ("manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64", "linux_x86_64"),
    ),
    Platform(
        name="Windows x86_64",
        asset=AssetPlatform.WINDOWS_X86_64,
        uv="x86_64-pc-windows-msvc",
        pip=("win_amd64",),
    ),
)
