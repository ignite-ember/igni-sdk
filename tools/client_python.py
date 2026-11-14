"""How igni-client's generated Python is spelled: names, docstrings and imports.

The leaves every part of ``tools/client_codegen.py`` shares: what a wire name
becomes in Python, how any text becomes a valid docstring, what a generated
module must import, and the error raised for a contract the generator cannot
turn into Python.
"""

from __future__ import annotations

import keyword
import re

from pydantic import BaseModel, Field

#: The first line of every generated module's docstring after its title.
BANNER = (
    "GENERATED from igni-core's RPC contract (version {version}) by igni-sdk's "
    "tools/client_codegen.py — do not edit. Run `make client-api` after refreshing "
    "contracts/rpc-contract.json."
)

#: Fields every message carries, which the bases in ``igni_client.wire`` declare.
ENVELOPE = ("type", "id", "session_id", "event_seq")

#: What a field may not be called in a Pydantic model: `BaseModel`'s own names.
_RESERVED = frozenset(
    {
        "json",
        "dict",
        "copy",
        "schema",
        "schema_json",
        "construct",
        "validate",
        "fields",
        "parse_obj",
        "parse_raw",
        "parse_file",
        "from_orm",
        "update_forward_refs",
    }
)


class ContractError(ValueError):
    """The contract says something this generator cannot turn into Python."""


class Imports(BaseModel):
    """What the generated module must import."""

    typing: set[str] = Field(default_factory=set)
    pydantic: set[str] = Field(default_factory=set)
    datetime: bool = False


def snake(name: str) -> str:
    """``activeForm`` → ``active_form``."""
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def field_name(prop: str) -> str:
    """The Python name of the wire field ``prop``: snake case, clear of keywords and
    of `BaseModel`'s own names (``json`` → ``json_``)."""
    python = snake(prop)
    if keyword.iskeyword(python) or python in _RESERVED:
        python += "_"
    return python


def pascal(name: str) -> str:
    """``read_process_tail`` → ``ReadProcessTail``."""
    return "".join(part[:1].upper() + part[1:] for part in re.split(r"[_.]", name) if part)


def docstring(text: str, indent: str) -> list[str]:
    """``text`` as a docstring at ``indent``, escaped so any text is valid Python."""
    body = text.strip().replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    if not body:
        return []
    lines = body.splitlines()
    if len(lines) == 1:
        closing = " " if body.endswith('"') else ""
        return [f'{indent}"""{body}{closing}"""']
    out = [f'{indent}"""{lines[0]}']
    out += [f"{indent}{line}" if line.strip() else "" for line in lines[1:]]
    out.append(f'{indent}"""')
    return out


__all__ = [
    "BANNER",
    "ENVELOPE",
    "ContractError",
    "Imports",
    "docstring",
    "field_name",
    "pascal",
    "snake",
]
