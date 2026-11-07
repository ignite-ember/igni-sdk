"""Requirement names, and requirement lines pinned by hash."""

from __future__ import annotations

import re


class Requirement:
    """PEP 503 names, the one way requirements are compared here."""

    _SEPARATORS = re.compile(r"[-_.]+")

    @classmethod
    def normalise(cls, name: str) -> str:
        return cls._SEPARATORS.sub("-", name).lower().strip()

    @classmethod
    def name_of(cls, requirement: str) -> str:
        return cls.normalise(re.split(r"[=<>!~;\[ ]", requirement, maxsplit=1)[0])

    @classmethod
    def of_wheel(cls, filename: str) -> str:
        """The distribution a wheel file is of."""
        return cls.normalise(filename.split("-")[0])


class HashedRequirements:
    """Requirement lines as `uv pip compile --generate-hashes` writes them.

    Each requirement is followed by its `--hash` options on continuation
    lines; they are joined into one line per requirement, which is a form
    pip reads in a requirements file.
    """

    @staticmethod
    def parse(text: str) -> list[str]:
        requirements: list[str] = []
        for raw in text.splitlines():
            line = raw.strip().removesuffix("\\").strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("--hash=") and requirements:
                requirements[-1] = f"{requirements[-1]} {line}"
            elif not line.startswith("-"):
                requirements.append(line)
        return requirements

    @staticmethod
    def bare(requirement: str) -> str:
        """The requirement without its hashes, for a command line."""
        return requirement.split(" --hash=", 1)[0]
