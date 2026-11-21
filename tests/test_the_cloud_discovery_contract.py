"""``contracts/cloud-discovery.schema.json`` says what igni server's ``/v1/me/cloud`` answers.

igni-sdk owns this contract (igni-core's ``docs/design/local-cloud-switch.md``
§2.1, §10): igni-server's model, igni-client and the desktop shell are each
tested against it, so a rule it states is a rule all three hold. Each rule
here gets a document that keeps it and one that breaks it — a schema that
stopped saying it would let the second through.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from scripts.sync_contracts import OWNED
from tests.siblings import REPO

SCHEMA_FILE = REPO / "contracts" / "cloud-discovery.schema.json"
SCHEMA: dict[str, Any] = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
DISCOVERY = Draft202012Validator(SCHEMA)


def part(name: str) -> Draft202012Validator:
    """A validator for `$defs/<name>`, resolving references within the file."""
    return Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]})


def answer(**changes: Any) -> dict[str, Any]:
    """The design's own example answer, with `changes`."""
    body: dict[str, Any] = copy.deepcopy(SCHEMA["$defs"]["CloudDiscovery"]["examples"][0])
    body.update(changes)
    return body


def valid(body: object, validator: Draft202012Validator = DISCOVERY) -> bool:
    return validator.is_valid(body)


def test_it_is_a_draft_2020_12_schema_igni_sdk_owns() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert SCHEMA["$id"] == "https://ignite-ember.sh/schema/cloud-discovery-1.json"
    assert "contracts/cloud-discovery.schema.json" in OWNED


def test_the_design_s_example_is_valid_word_for_word() -> None:
    assert answer() == {
        "cloud": "available",
        "reason": None,
        "gateway_url": "https://fleet.acme.example",
        "mode": "local_and_cloud",
        "events_owner": "local",
        "group": {"id": "7f3e9a52-4c1d-4b8e-9f2a-0d6c3b1e5a77", "name": "Engineering"},
        "producer": "person:2b9c41d0-8e7f-4a3b-b5c6-1d2e3f4a5b6c",
    }
    assert valid(answer())


@pytest.mark.parametrize(
    ("name", "index"),
    [
        (name, index)
        for name, definition in SCHEMA["$defs"].items()
        for index in range(len(definition.get("examples", [])))
    ],
)
def test_every_example_in_the_file_is_valid_for_its_own_part(name: str, index: int) -> None:
    assert valid(SCHEMA["$defs"][name]["examples"][index], part(name))


def test_the_examples_cover_each_reason_and_each_mode() -> None:
    examples = SCHEMA["$defs"]["CloudDiscovery"]["examples"]
    assert {e["reason"] for e in examples} == {
        None,
        "fleet_not_configured",
        "group_local_only",
        "inactive",
        "not_licensed",
    }
    assert {e["mode"] for e in examples} == {"local", "cloud", "local_and_cloud"}


def test_every_field_is_required() -> None:
    for field in answer():
        body = answer()
        del body[field]
        assert not valid(body), field


def test_a_field_igni_server_adds_later_is_allowed() -> None:
    assert valid(answer(vm_profile="standard"))
    assert valid(answer(group={"id": "g", "name": "G", "colour": "red"}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cloud", "maybe"),
        ("reason", "some_new_reason"),
        ("mode", "hybrid"),
        ("events_owner", "both"),
        ("producer", "app:bot"),
        ("producer", "person:"),
        ("gateway_url", "fleet.acme.example"),
        ("gateway_url", "wss://fleet.acme.example"),
        ("gateway_url", ""),
        ("group", {"id": "", "name": "G"}),
        ("group", {"name": "G"}),
        ("group", "Engineering"),
    ],
)
def test_igni_server_sends_only_the_values_the_contract_names(field: str, value: object) -> None:
    assert not valid(answer(**{field: value}))


def test_a_gateway_may_be_https_or_a_lab_s_plain_http_with_a_path() -> None:
    assert valid(answer(gateway_url="https://fleet.acme.example/gw"))
    assert valid(answer(gateway_url="http://10.0.0.5:8080"))


def test_a_person_in_no_group_has_a_null_group() -> None:
    assert valid(answer(group=None))


def test_available_has_no_reason_and_a_gateway() -> None:
    assert not valid(answer(reason="inactive"))
    assert not valid(answer(gateway_url=None))


def test_unavailable_always_says_why() -> None:
    assert valid(answer(cloud="unavailable", reason="inactive"))
    assert not valid(answer(cloud="unavailable", reason=None))


def test_the_gateway_is_null_exactly_when_fleet_is_not_configured() -> None:
    assert valid(answer(cloud="unavailable", reason="fleet_not_configured", gateway_url=None))
    assert not valid(answer(cloud="unavailable", reason="inactive", gateway_url=None))
    assert not valid(answer(cloud="unavailable", reason="fleet_not_configured"))


def test_local_mode_has_no_cloud_igni_and_pulls_events_locally() -> None:
    local = {"cloud": "unavailable", "reason": "group_local_only", "mode": "local"}
    assert valid(answer(**local))
    assert not valid(answer(**{**local, "cloud": "available", "reason": None}))
    assert not valid(answer(**{**local, "events_owner": "cloud"}))


def test_cloud_mode_pulls_events_in_the_cloud() -> None:
    assert valid(answer(mode="cloud", events_owner="cloud"))
    assert not valid(answer(mode="cloud", events_owner="local"))


def test_local_and_cloud_lets_either_side_pull() -> None:
    assert valid(answer(events_owner="local"))
    assert valid(answer(events_owner="cloud"))


def test_group_local_only_is_said_only_of_a_local_group() -> None:
    assert not valid(answer(cloud="unavailable", reason="group_local_only"))
    assert not valid(
        answer(cloud="unavailable", reason="group_local_only", mode="cloud", events_owner="cloud")
    )


def test_the_events_owner_body_is_one_known_owner_and_nothing_else() -> None:
    body = part("EventsOwnerRequest")
    assert valid({"owner": "cloud"}, body) and valid({"owner": "local"}, body)
    assert not valid({}, body)
    assert not valid({"owner": "both"}, body)
    assert not valid({"owner": "cloud", "force": True}, body)


def test_the_mode_forbids_refusal_names_itself() -> None:
    forbids = part("ModeForbids")
    assert valid({"error": "mode_forbids"}, forbids)
    assert valid({"error": "mode_forbids", "detail": "local mode"}, forbids)
    assert not valid({"error": "conflict"}, forbids)
    assert not valid({}, forbids)


def test_a_refusal_carries_a_detail_or_an_oauth_error() -> None:
    refusal = part("Refusal")
    assert valid({"detail": "Not authenticated"}, refusal)
    assert valid({"error": "invalid_token", "error_description": "expired"}, refusal)
    assert not valid({}, refusal)
    assert not valid({"error_description": "expired"}, refusal)
    assert not valid({"detail": 403}, refusal)
