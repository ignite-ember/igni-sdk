"""Each igni-client method's TypeScript signature, read from ``api.generated.ts``.

The reference shows a method's Python signature and, under it, the same
method in TypeScript, so a reader on either SDK sees what they call. Each
generated TypeScript method names the wire method it calls in its body
(``this.caller.rpc("list_sessions", …)``), which is how a signature is
found for a wire name without a second naming table.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.site_page import DocsError

#: A method's first line in a generated class: two spaces in, its name, ``(``.
_START = re.compile(r"^  (?!constructor\()(?P<name>[a-z_][a-z0-9_]*)\(")
#: The wire method a body calls: the first string a ``caller`` call is handed.
_WIRE = re.compile(r"this\.caller\.\w+(?:<[^>]*>)?\(\s*\"(?P<wire>[a-z0-9_]+)\"")

#: The longest a signature stays on one line.
_WIDTH = 88


class TsSignatures:
    """``api.generated.ts``'s method signatures, by the wire method each calls."""

    def __init__(self, by_wire: dict[str, str]) -> None:
        self._by_wire = by_wire

    @classmethod
    def read(cls, path: Path) -> TsSignatures:
        lines = path.read_text(encoding="utf-8").split("\n")
        by_wire: dict[str, str] = {}
        i = 0
        while i < len(lines):
            if not _START.match(lines[i]):
                i += 1
                continue
            head: list[str] = []
            while not lines[i].rstrip().endswith("{"):
                head.append(lines[i].strip())
                i += 1
            head.append(lines[i].strip()[:-1].rstrip())
            body: list[str] = []
            i += 1
            while i < len(lines) and lines[i] != "  }":
                body.append(lines[i])
                i += 1
            found = _WIRE.search("\n".join(body))
            if found is not None:
                by_wire.setdefault(found.group("wire"), _joined(head))
        return cls(by_wire)

    def of(self, wire: str) -> str:
        """``wire``'s TypeScript signature, laid out to the reference's width."""
        try:
            return _laid_out(self._by_wire[wire])
        except KeyError:
            raise DocsError(
                f"api.generated.ts has no method calling {wire}: igni-client's two SDKs differ"
            ) from None


def _joined(head: list[str]) -> str:
    """A signature written over several lines, on one: no space inside its brackets."""
    text = " ".join(part for part in head if part)
    return re.sub(r"\(\s+", "(", re.sub(r",?\s+\)", ")", text))


def _laid_out(signature: str) -> str:
    """One line when it fits, else one parameter a line."""
    if len(signature) <= _WIDTH:
        return signature
    name, rest = signature.split("(", 1)
    params, result = _split_params(rest)
    if not params:
        return signature
    return name + "(\n" + "".join(f"  {p},\n" for p in params) + ")" + result


def _split_params(rest: str) -> tuple[list[str], str]:
    """The parameters inside ``(…)`` — split at top-level commas — and what follows ``)``."""
    depth = 0
    params: list[str] = []
    current = ""
    for index, char in enumerate(rest):
        if char in "(<{[":
            depth += 1
        elif char in ")>}]":
            if depth == 0 and char == ")":
                if current.strip():
                    params.append(current.strip())
                return params, rest[index + 1 :]
            depth -= 1
        if char == "," and depth == 0:
            params.append(current.strip())
            current = ""
            continue
        current += char
    return params, ""


__all__ = ["TsSignatures"]
