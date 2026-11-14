"""The grants a service sends to igni's token endpoint: typed, and on the wire the same forms as before."""

from __future__ import annotations

from urllib.parse import parse_qsl

import pytest
from pydantic import ValidationError

from igni_service import IgniService
from igni_service.grants import (
    AuthorizationCodeGrant,
    ClientCredentialsGrant,
    Grant,
    RefreshTokenGrant,
)
from igni_service.testing import FakeIgni
from igni_service.token_endpoint import TokenEndpoint
from igni_service.urls import IgniPaths

from .conftest import ORG


@pytest.mark.parametrize(
    ("grant", "form"),
    [
        (ClientCredentialsGrant(), {"grant_type": "client_credentials"}),
        (
            ClientCredentialsGrant(organisation=ORG),
            {"grant_type": "client_credentials", "organisation": ORG},
        ),
        (
            ClientCredentialsGrant(scope="revocations"),
            {"grant_type": "client_credentials", "scope": "revocations"},
        ),
        (
            AuthorizationCodeGrant(code="c", code_verifier="v", redirect_uri="https://s.test/cb"),
            {
                "grant_type": "authorization_code",
                "code": "c",
                "code_verifier": "v",
                "redirect_uri": "https://s.test/cb",
            },
        ),
        (
            RefreshTokenGrant(refresh_token="r"),
            {"grant_type": "refresh_token", "refresh_token": "r"},
        ),
    ],
)
def test_each_grant_is_the_form_it_replaced_grant_type_first_and_nothing_unset(
    grant: Grant, form: dict[str, str]
) -> None:
    assert list(grant.form().items()) == list(form.items())


def test_an_empty_string_is_still_sent() -> None:
    assert ClientCredentialsGrant(organisation="").form() == {
        "grant_type": "client_credentials",
        "organisation": "",
    }


def test_a_grant_missing_what_it_needs_is_refused_before_anything_is_sent() -> None:
    with pytest.raises(ValidationError):
        RefreshTokenGrant()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        AuthorizationCodeGrant(code="c", redirect_uri="https://s.test/cb")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ClientCredentialsGrant(grant_type="password")  # type: ignore[arg-type]


async def test_the_endpoint_posts_the_grant_form_then_the_assertion(
    igni: IgniService, fake: FakeIgni
) -> None:
    endpoint = TokenEndpoint(
        igni.connection.server, igni.connection.registration, igni.connection.key
    )

    await endpoint.grant(ClientCredentialsGrant(organisation=ORG))

    [seen] = fake.traffic.requests_to(IgniPaths.TOKEN)
    keys = [key for key, _ in parse_qsl(seen.body.decode(), keep_blank_values=True)]
    assert keys == ["grant_type", "organisation", "client_assertion_type", "client_assertion"]


async def test_the_endpoint_takes_a_grant_not_the_dict_it_used_to(
    igni: IgniService, fake: FakeIgni
) -> None:
    endpoint = TokenEndpoint(
        igni.connection.server, igni.connection.registration, igni.connection.key
    )

    with pytest.raises(AttributeError, match="'dict' object has no attribute 'form'"):
        await endpoint.grant({"grant_type": "client_credentials"})  # type: ignore[arg-type]

    assert fake.traffic.requests_to(IgniPaths.TOKEN) == []
