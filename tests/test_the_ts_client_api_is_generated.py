"""The TypeScript igni-client is igni-core's RPC contract, typed — and current.

``tools/client_ts.py`` writes ``@ignite-ember/igni-client``'s models
(``models.generated.ts``) and methods (``api.generated.ts``) from the same
``contracts/rpc-contract.json`` the Python client is generated from, through the
same :class:`~tools.client_plan.Plan`. This holds the checked-in TypeScript to
the contract, and holds the two clients to each other: a method, a model or a
followed call in one but not the other fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools import client_ts
from tools.client_api import ApiGenerator
from tools.client_contract import RpcContract
from tools.client_models import ModelsGenerator
from tools.client_names import FOLLOWED
from tools.client_plan import Plan

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = RpcContract.read()
PLAN = Plan(CONTRACT)
MODELS_TS = (ROOT / client_ts.MODELS_OUTPUT).read_text(encoding="utf-8")
API_TS = (ROOT / client_ts.API_OUTPUT).read_text(encoding="utf-8")

#: Each METHODS entry's wire name and the fields a parity check compares.
_ENTRY = re.compile(
    r'"(?P<wire>\w+)": \{ wire: "\w+", python: "(?P<python>[\w.]+)", '
    r'scope: "(?P<scope>\w+)", access: "(?P<access>\w+)", reply: "(?P<reply>\w+)", '
    r"streams: \[[^\]]*\], mayStream: \[[^\]]*\], duration: \"\w*\", "
    r"timeoutSeconds: (?P<timeout>\w+|null), correlate: (?P<correlate>null|\{[^}]*\}), "
    r"followed: (?P<followed>true|false) \}"
)


def _ts_methods() -> dict[str, dict[str, str]]:
    return {m.group("wire"): m.groupdict() for m in _ENTRY.finditer(API_TS)}


def test_the_checked_in_typescript_is_what_the_contract_generates() -> None:
    stale = client_ts.stale(ROOT)
    assert not stale, (
        f"generated from an older contract: {[str(p.relative_to(ROOT)) for p in stale]}. "
        "Run `make client-api`."
    )


def test_both_generators_run_over_the_contract_without_error() -> None:
    assert ModelsGenerator(PLAN).generate()
    assert ApiGenerator(PLAN).generate()
    assert client_ts.models_ts(PLAN)
    assert client_ts.api_ts(PLAN)


def test_the_two_clients_place_the_same_methods() -> None:
    """The TypeScript METHODS table names exactly the methods the Python one does."""
    assert set(_ts_methods()) == set(PLAN.placements)


def test_each_method_carries_the_contract_s_metadata_in_both() -> None:
    for wire, entry in _ts_methods().items():
        method = CONTRACT.methods[wire]
        placement = PLAN.placements[wire]
        assert entry["python"] == placement.path, wire
        assert entry["scope"] == method.scope, wire
        assert entry["access"] == method.access, wire
        assert entry["reply"] == method.reply, wire
        expected_timeout = "null" if method.timeout_seconds is None else str(method.timeout_seconds)
        assert entry["timeout"] == expected_timeout, wire
        assert entry["followed"] == str(wire in FOLLOWED).lower(), wire


def test_both_clients_know_the_same_wire_messages() -> None:
    """EVENT_TYPES in TypeScript is the set of messages igni may send, as Python's is."""
    ts_events = set(re.findall(r'"([\w]+)",', _event_block(MODELS_TS, "EVENT_TYPES")))
    python_events = {
        t for t, m in CONTRACT.messages.items() if m.direction in ("to_client", "both")
    }
    assert ts_events == python_events
    ts_pushes = set(re.findall(r'"([\w]+)",', _event_block(MODELS_TS, "PUSH_CHANNELS")))
    assert ts_pushes == set(CONTRACT.push_channels)


def test_every_followed_method_has_an_event_alias() -> None:
    for wire in FOLLOWED:
        from tools.client_python import pascal

        assert f"export type {pascal(wire)}Event =" in API_TS, wire


def test_the_generated_files_carry_the_contract_s_version() -> None:
    for text in (MODELS_TS, API_TS):
        assert f"(version {CONTRACT.version})" in text


def _event_block(text: str, name: str) -> str:
    start = text.index(f"export const {name}")
    return text[start : text.index("]);", start)]
