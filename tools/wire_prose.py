"""igni-core's contract text, said the way igni-client's Python API says it.

igni-core writes one description per method and field, for the wire: the
field is ``whenToUse``, the method ``run_workflow``, and every session method
takes the session in ``session_id``. igni-client's reader has
``when_to_use``, ``session.workflows.run()`` and a ``Session`` that is one
session already. ``WireProse`` is the one place that turns the first into
the second, and each turn is a named method:

* ``python_names`` — a wire name in code font becomes the Python attribute or
  call it is;
* ``without_own_session`` — "`session_id` names the session" goes from the
  text of a method whose ``Session`` supplies it;
* ``argument_free`` — an opening "Takes no arguments (...)." is taken out, so
  the page says it once, where a parameter table would be.

The contract's text itself is left as igni-core wrote it: the wire is what
it describes, and the README's reference shows it so.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from tools.client_contract import RpcContract
from tools.client_names import OWN_SESSION_ARG
from tools.client_plan import Placement
from tools.client_python import field_name

_ROLE = re.compile(r":(?:class|meth|func|attr|data|mod|exc):`~?([^`]+)`")
_CODE_NAME = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
_OWN_SESSION = re.compile(r"`session_id` names the session[.;]\s*")
_NO_ARGUMENTS = re.compile(r"Takes no arguments(?: \(([^)]*)\))?\.\s*")


def rst(text: str) -> str:
    """igni-core's reStructuredText-flavoured docstrings, as Markdown."""
    return _ROLE.sub(r"`\1`", text).replace("``", "`")


def cell(text: str) -> str:
    """``text`` fit for one cell of a Markdown table."""
    return " ".join(text.split()).replace("|", "\\|")


class ArgumentFreeText(BaseModel):
    """A paragraph without its opening "Takes no arguments.", and what that said in brackets."""

    text: str
    note: str = ""

    @classmethod
    def of(cls, text: str) -> ArgumentFreeText:
        match = _NO_ARGUMENTS.match(text)
        if match is None:
            return cls(text=text)
        return cls(text=text[match.end() :], note=match.group(1) or "")


class WireProse:
    """The contract's prose for a Python page: it names the Python call or attribute."""

    def __init__(self, contract: RpcContract, placements: dict[str, Placement]) -> None:
        self.placements = placements
        #: Every field name the contract spells in the wire's camelCase.
        self.wire_fields: frozenset[str] = frozenset(
            name for schema in contract.defs.values() for name in schema.get("properties", {})
        )

    def own_session(self, wire: str) -> bool:
        """Whether ``wire`` is a ``Session`` method whose ``session_id`` the session supplies."""
        placement = self.placements.get(wire)
        return placement is not None and placement.owner == "session" and wire in OWN_SESSION_ARG

    def prose(self, text: str, wire: str | None = None) -> str:
        """``text`` as Markdown, its wire names said the Python way."""
        text = rst(text)
        if wire is not None:
            text = self.without_own_session(text, wire)
        return self.python_names(text)

    def without_own_session(self, text: str, wire: str) -> str:
        """``text`` without "`session_id` names the session", when the session supplies it."""
        return _OWN_SESSION.sub("", text) if self.own_session(wire) else text

    def python_names(self, text: str) -> str:
        """Every wire name in code font in ``text``, as the Python API says it."""
        return _CODE_NAME.sub(self._python_name, text)

    def _python_name(self, match: re.Match[str]) -> str:
        token = match.group(1)
        placement = self.placements.get(token)
        if placement is not None and "_" in token and token not in self.wire_fields:
            return f"`{placement.path}()`"
        if token in self.wire_fields and field_name(token) != token:
            return f"`{field_name(token)}`"
        return match.group(0)

    @staticmethod
    def argument_free(paragraphs: list[str]) -> list[ArgumentFreeText]:
        """Each paragraph without its opening "Takes no arguments."."""
        return [ArgumentFreeText.of(p) for p in paragraphs]


__all__ = ["ArgumentFreeText", "WireProse", "cell", "rst"]
