"""The bearer tokens the fake issues: format, uniqueness and which set each belongs to."""

from __future__ import annotations

import re

import pytest

from igni_service.testing_bearers import BearerTokens, TokenHolder

SERVICE = TokenHolder(client_id="svc", org_id="org-1")
APP = TokenHolder(client_id="app-1", org_id="org-1")


def test_a_service_token_is_its_prefix_and_a_random_hex_and_its_holder_is_remembered() -> None:
    bearers = BearerTokens()

    token = bearers.issue_service(SERVICE, "svc")

    assert re.fullmatch(r"svc-[0-9a-f]{32}", token)
    assert bearers.service_holder(token) == SERVICE


def test_an_app_token_is_app_and_a_random_hex_and_its_holder_is_remembered() -> None:
    bearers = BearerTokens()

    token = bearers.issue_app(APP)

    assert re.fullmatch(r"app-[0-9a-f]{32}", token)
    assert bearers.app_holder(token) == APP


def test_two_tokens_for_the_same_holder_differ_and_both_hold() -> None:
    bearers = BearerTokens()

    first, second = bearers.issue_service(SERVICE, "svc"), bearers.issue_service(SERVICE, "svc")

    assert first != second
    assert bearers.service_holder(first) == bearers.service_holder(second) == SERVICE
    first_app, second_app = bearers.issue_app(APP), bearers.issue_app(APP)
    assert first_app != second_app


@pytest.mark.parametrize("bearer", ["", "svc-", "nobody", "Bearer x"])
def test_a_bearer_nobody_issued_has_no_holder(bearer: str) -> None:
    bearers = BearerTokens()
    bearers.issue_service(SERVICE, "svc")
    bearers.issue_app(APP)

    assert bearers.service_holder(bearer) is None
    assert bearers.app_holder(bearer) is None


def test_a_service_token_is_not_an_app_s_and_the_reverse() -> None:
    bearers = BearerTokens()
    service_token = bearers.issue_service(SERVICE, "svc")
    app_token = bearers.issue_app(APP)

    assert bearers.app_holder(service_token) is None
    assert bearers.service_holder(app_token) is None


def test_expiring_service_tokens_leaves_the_apps_alone() -> None:
    bearers = BearerTokens()
    one, two = bearers.issue_service(SERVICE, "svc"), bearers.issue_service(SERVICE, "svc")
    app_token = bearers.issue_app(APP)

    bearers.expire_service()

    assert bearers.service_holder(one) is None and bearers.service_holder(two) is None
    assert bearers.app_holder(app_token) == APP
    assert bearers.service == {}


def test_expiring_with_nothing_issued_is_fine_and_tokens_after_it_hold() -> None:
    bearers = BearerTokens()

    bearers.expire_service()
    token = bearers.issue_service(SERVICE, "svc")

    assert bearers.service_holder(token) == SERVICE


def test_a_holder_with_no_organisation_is_an_empty_one_and_is_frozen() -> None:
    holder = TokenHolder(client_id="svc")

    assert holder.org_id == ""
    assert TokenHolder() == TokenHolder(client_id="", org_id="")
    with pytest.raises(ValueError):
        holder.org_id = "x"
