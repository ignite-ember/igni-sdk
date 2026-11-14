"""The fake's client registry: what it registers, refuses, approves and revokes.

Driven at the registry itself, with the bodies a service posts, so each
refusal and each answer is seen as igni's answer and not through the SDK
that sends it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from igni_service.crypto import RsaKeyPair
from igni_service.testing_clients import (
    ClientKind,
    ClientState,
    FakeClientRegistry,
    RegistrationResponse,
)
from igni_service.testing_wire import RoutedCall, SeenRequest


def registration(
    pair: RsaKeyPair,
    *,
    name: str = "Tickets",
    uri: str = "https://tickets.test/",
    kind: str = "service",
    keys: list[dict[str, Any]] | None = None,
) -> RoutedCall:
    body = {
        "client_name": name,
        "client_uri": uri,
        "kind": kind,
        "jwks": {"keys": keys if keys is not None else [pair.public_jwk().as_dict()]},
    }
    return posted(json.dumps(body).encode())


def posted(body: bytes) -> RoutedCall:
    return RoutedCall(seen=SeenRequest(method="POST", path="/v1/clients", headers={}, body=body))


def test_the_same_key_registers_once_and_is_answered_as_the_first_time() -> None:
    registry = FakeClientRegistry()
    pair = RsaKeyPair.generate()

    first = registry.register(registration(pair))
    again = registry.register(registration(pair, name="Renamed", uri="https://other.test"))

    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json() == first.json()
    assert len(registry.clients) == 1
    assert first.json()["client_id"] in registry.clients
    assert first.json()["client_name"] == "Tickets"
    assert first.json()["client_uri"] == "https://tickets.test"


def test_a_new_registration_is_pending_and_answers_its_wire_fields_only() -> None:
    registry = FakeClientRegistry()
    pair = RsaKeyPair.generate()

    answer = registry.register(registration(pair)).json()

    assert answer == {
        "client_id": answer["client_id"],
        "client_id_issued_at": 0,
        "client_name": "Tickets",
        "client_uri": "https://tickets.test",
        "kind": "service",
        "redirect_uris": [],
        "token_endpoint_auth_method": "private_key_jwt",
        "state": "pending",
        "thumbprint": pair.thumbprint(),
    }
    assert set(answer) == set(RegistrationResponse.model_fields)
    assert registry.registration is registry.get(answer["client_id"])
    assert registry.owner_of_thumbprint(pair.thumbprint()) is registry.registration


def test_a_second_key_makes_a_second_client_and_registration_is_the_first() -> None:
    registry = FakeClientRegistry()
    first, second = RsaKeyPair.generate(), RsaKeyPair.generate()

    registry.register(registration(first))
    registry.register(registration(second, name="Other"))

    assert len(registry.clients) == 2
    assert registry.registration is not None
    assert registry.registration.thumbprint == first.thumbprint()
    owner = registry.owner_of_thumbprint(second.thumbprint())
    assert owner is not None
    assert owner.client_name == "Other"


def test_an_empty_registry_has_no_registration_no_owner_and_no_client() -> None:
    registry = FakeClientRegistry()

    assert registry.registration is None
    assert registry.owner_of_thumbprint("nothing") is None
    assert registry.get("nothing") is None


def test_a_key_an_app_holds_is_answered_with_the_apps_registration() -> None:
    registry = FakeClientRegistry()
    pair = RsaKeyPair.generate()
    registry.add_app("app-1", "org-acme", "Notes", pair)

    answer = registry.register(registration(pair, kind="service")).json()

    assert (answer["client_id"], answer["kind"], answer["state"]) == ("app-1", "app", "approved")
    assert len(registry.clients) == 1


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"not json", id="not json"),
        pytest.param(b"{}", id="no metadata"),
        pytest.param(b'{"client_name": "x"}', id="no uri or keys"),
    ],
)
def test_a_body_that_is_not_client_metadata_is_refused(body: bytes) -> None:
    registry = FakeClientRegistry()

    response = registry.register(posted(body))

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client_metadata"
    assert registry.clients == {}


def test_other_than_exactly_one_public_key_is_refused() -> None:
    registry = FakeClientRegistry()
    one, two = RsaKeyPair.generate(), RsaKeyPair.generate()
    both = [one.public_jwk().as_dict(), two.public_jwk().as_dict()]

    none = registry.register(registration(one, keys=[]))
    several = registry.register(registration(one, keys=both))

    for response in (none, several):
        assert response.status_code == 400
        assert response.json() == {
            "error": "invalid_client_metadata",
            "error_description": "exactly one public key is required",
        }
    assert registry.clients == {}


def test_a_key_that_carries_its_private_member_is_refused() -> None:
    registry = FakeClientRegistry()
    pair = RsaKeyPair.generate()
    leaked = {**pair.public_jwk().as_dict(), "d": "secret"}

    response = registry.register(registration(pair, keys=[leaked]))

    assert response.status_code == 400
    assert response.json()["error_description"] == "exactly one public key is required"
    assert registry.clients == {}


@pytest.mark.parametrize(
    ("uri", "kind", "words"),
    [
        ("tickets.test", "service", "is not an absolute http(s) URL"),
        ("https://tickets.test/?a=1", "service", "must not have a query or a fragment"),
        ("https://tickets.test", "robot", "is not a valid ClientKind"),
    ],
)
def test_an_address_igni_cannot_normalise_or_a_kind_it_lacks_is_refused(
    uri: str, kind: str, words: str
) -> None:
    registry = FakeClientRegistry()

    response = registry.register(registration(RsaKeyPair.generate(), uri=uri, kind=kind))

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client_metadata"
    assert words in response.json()["error_description"]
    assert registry.clients == {}


def test_a_registration_of_kind_app_is_kept_as_an_app() -> None:
    registry = FakeClientRegistry()

    answer = registry.register(registration(RsaKeyPair.generate(), kind="app")).json()

    assert answer["kind"] == "app"
    assert answer["state"] == "pending"


def test_approve_and_revoke_move_one_client_and_leave_the_others() -> None:
    registry = FakeClientRegistry()
    first = registry.register(registration(RsaKeyPair.generate())).json()["client_id"]
    second = registry.register(registration(RsaKeyPair.generate())).json()["client_id"]

    registry.approve(first)
    assert states(registry) == {first: "approved", second: "pending"}
    registry.revoke(second)
    assert states(registry) == {first: "approved", second: "revoked"}
    assert registry.clients[first].is_approved
    assert registry.clients[second].is_revoked


def test_approve_and_revoke_without_an_id_move_every_client() -> None:
    registry = FakeClientRegistry()
    for _ in range(2):
        registry.register(registration(RsaKeyPair.generate()))

    registry.approve()
    assert set(states(registry).values()) == {"approved"}
    registry.revoke()
    assert set(states(registry).values()) == {"revoked"}
    registry.approve()
    assert set(states(registry).values()) == {"approved"}


def test_an_unknown_id_changes_nothing_and_does_not_raise() -> None:
    registry = FakeClientRegistry()
    client_id = registry.register(registration(RsaKeyPair.generate())).json()["client_id"]

    registry.approve("nobody")
    registry.revoke("nobody")
    FakeClientRegistry().approve()

    assert states(registry) == {client_id: "pending"}


def test_an_app_is_approved_by_being_registered_and_keeps_its_organisation() -> None:
    registry = FakeClientRegistry()
    pair = RsaKeyPair.generate()

    client = registry.add_app("app-1", "org-acme", "Notes", pair)

    assert registry.get("app-1") is client
    assert (client.kind, client.state, client.org_id) == (
        ClientKind.APP,
        ClientState.APPROVED,
        "org-acme",
    )
    assert (client.client_name, client.client_uri, client.redirect_uris) == ("Notes", "", [])
    assert client.thumbprint == pair.thumbprint()
    assert client.jwk == pair.public_jwk()


def test_an_app_without_a_name_is_named_by_its_id_and_a_second_registration_replaces_it() -> None:
    registry = FakeClientRegistry()

    registry.add_app("app-1", "org-acme", "", RsaKeyPair.generate())
    replacement = registry.add_app("app-1", "org-other", "Notes", RsaKeyPair.generate())

    assert registry.clients == {"app-1": replacement}
    assert replacement.org_id == "org-other"
    unnamed = FakeClientRegistry().add_app("app-2", "org-acme", "", RsaKeyPair.generate())
    assert unnamed.client_name == "app-2"


def test_the_answer_for_a_client_never_carries_its_key_or_organisation() -> None:
    registry = FakeClientRegistry()
    client = registry.add_app("app-1", "org-acme", "Notes", RsaKeyPair.generate())

    answer = client.registration_response()

    assert answer.client_id == "app-1"
    assert answer.state is ClientState.APPROVED
    assert answer.token_endpoint_auth_method == "private_key_jwt"
    dumped = answer.model_dump(mode="json")
    assert "jwk" not in dumped
    assert "org_id" not in dumped
    assert set(dumped) == set(RegistrationResponse.model_fields)


def states(registry: FakeClientRegistry) -> dict[str, str]:
    return {client_id: client.state.value for client_id, client in registry.clients.items()}
