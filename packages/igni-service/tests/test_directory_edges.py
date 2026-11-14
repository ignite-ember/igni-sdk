"""The directory's edges: refusals, batching, blanks, the cache's age and what a member reads as.

`DirectoryClient` is real; what it asks through is a scripted stand-in for the service's tokens,
so each test decides what igni answers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import httpx
import pytest

from igni_service import IgniUnavailable, Member
from igni_service.directory import Directory, DirectoryClient
from igni_service.service_tokens import ServiceTokens
from igni_service.testing import ManualClock
from igni_service.urls import IgniPaths

from .conftest import ORG

PEOPLE = f"{IgniPaths.DIRECTORY}/people"


def member(user_id: str, **fields: Any) -> dict[str, Any]:
    return {"user_id": user_id, "email": f"{user_id}@acme.test", "name": user_id.title(), **fields}


class Asked:
    """Stands in for `ServiceTokens`: answers each request from `answer` and keeps them."""

    def __init__(self, answer: Callable[[str, str, dict[str, Any]], httpx.Response]) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str, str, dict[str, Any]]] = []

    async def request(
        self, method: str, path: str, *, org_id: str, **kwargs: Any
    ) -> httpx.Response:
        self.calls.append((method, path, org_id, kwargs))
        return self.answer(method, path, kwargs)

    def client(self, clock: ManualClock | None = None) -> DirectoryClient:
        return DirectoryClient(cast(ServiceTokens, self), clock=clock)


def says(status: int, body: Any = None, *, text: str = "") -> Asked:
    def answer(method: str, path: str, kwargs: dict[str, Any]) -> httpx.Response:
        return (
            httpx.Response(status, json=body)
            if body is not None
            else httpx.Response(status, text=text)
        )

    return Asked(answer)


def echoing_members(method: str, path: str, kwargs: dict[str, Any]) -> httpx.Response:
    """igni's resolve: every identity asked is a member whose user id and address it is."""
    asked = kwargs["json"]["identities"]
    return httpx.Response(200, json={"people": [member(name) for name in asked]})


class TestWhatIgniMayAnswer:
    @pytest.mark.parametrize("status", [400, 403, 404, 500, 503])
    @pytest.mark.parametrize("ask", ["organisation", "members", "resolve"])
    async def test_a_status_other_than_200_is_igni_unavailable(self, ask: str, status: int) -> None:
        client = says(status, text="no").client()
        with pytest.raises(IgniUnavailable, match=str(status)):
            if ask == "organisation":
                await client.organisation(ORG)
            elif ask == "members":
                await client.members(ORG)
            else:
                await client.resolve(ORG, ["u-max"])

    @pytest.mark.parametrize("status", [400, 403, 500])
    async def test_a_person_igni_could_not_look_up_is_not_a_missing_person(
        self, status: int
    ) -> None:
        with pytest.raises(IgniUnavailable, match=str(status)):
            await says(status).client().person(ORG, "u-max")

    @pytest.mark.parametrize("body", [None, "text", ["a"], {"people": "x"}, {"people": [{"x": 1}]}])
    async def test_an_answer_that_is_not_the_expected_shape_is_igni_unavailable(
        self, body: Any
    ) -> None:
        client = Asked(
            lambda *_: (
                httpx.Response(200, text="not json")
                if body is None
                else httpx.Response(200, json=body)
            )
        ).client()

        with pytest.raises(IgniUnavailable, match="something else"):
            await client.members(ORG)
        with pytest.raises(IgniUnavailable, match="something else"):
            await client.resolve(ORG, ["u"])

    async def test_an_organisation_or_a_person_with_the_wrong_shape_is_igni_unavailable(
        self,
    ) -> None:
        client = says(200, {"name": "no id"}).client()

        with pytest.raises(IgniUnavailable, match="something else"):
            await client.organisation(ORG)
        with pytest.raises(IgniUnavailable, match="something else"):
            await client.person(ORG, "u")

    async def test_a_token_that_cannot_be_had_is_the_error_the_caller_sees(self) -> None:
        def unreachable(*_: Any) -> httpx.Response:
            raise IgniUnavailable("could not reach igni server")

        with pytest.raises(IgniUnavailable, match="could not reach"):
            await Asked(unreachable).client().resolve(ORG, ["u"])

    async def test_a_member_list_is_what_igni_listed_with_their_defaults(self) -> None:
        client = says(200, {"people": [{"user_id": "u-1"}]}).client()

        [only] = await client.members(ORG, query="u", limit=5, include_former=True)

        assert only == Member(user_id="u-1")
        assert (only.role, only.status, only.super_admin) == ("member", "active", False)
        [(method, path, org, kwargs)] = client_calls(client)
        assert (method, path, org) == ("GET", f"{IgniPaths.DIRECTORY}/members", ORG)
        assert kwargs["params"] == {"query": "u", "limit": 5, "include_former": "true"}


def client_calls(client: DirectoryClient) -> list[tuple[str, str, str, dict[str, Any]]]:
    return cast(Asked, client._tokens).calls


class TestResolveBatches:
    async def test_more_than_five_hundred_identities_go_in_batches_of_at_most_five_hundred(
        self,
    ) -> None:
        asked = Asked(echoing_members)
        names = [f"u-{n}" for n in range(1201)]

        found = await asked.client().resolve(ORG, names)

        sizes = [len(kwargs["json"]["identities"]) for *_, kwargs in asked.calls]
        assert sizes == [500, 500, 201]
        assert all(path == f"{PEOPLE}/resolve" and org == ORG for _, path, org, _ in asked.calls)
        assert {name for name in names} <= set(found)

    async def test_exactly_five_hundred_is_one_batch(self) -> None:
        asked = Asked(echoing_members)

        await asked.client().resolve(ORG, [f"u-{n}" for n in range(500)])

        assert len(asked.calls) == 1

    async def test_blanks_and_repeats_are_not_asked_twice(self) -> None:
        asked = Asked(echoing_members)

        found = await asked.client().resolve(
            ORG, ["", "  ", "u-1", " u-1 ", "u-1", "U-1", "u-2", "\t"]
        )

        [(_, _, _, kwargs)] = asked.calls
        assert kwargs["json"] == {"identities": ["u-1", "U-1", "u-2"]}
        assert set(found) == {"u-1", "u-1@acme.test", "u-2", "u-2@acme.test"}

    @pytest.mark.parametrize("identities", [[], [""], ["   ", "\n"]])
    async def test_nothing_to_look_up_asks_nothing(self, identities: list[str]) -> None:
        asked = Asked(echoing_members)

        assert await asked.client().resolve(ORG, identities) == {}
        assert asked.calls == []

    async def test_a_member_without_an_address_is_found_by_their_user_id_only(self) -> None:
        client = says(200, {"people": [{"user_id": "U-Bot"}]}).client()

        found = await client.resolve(ORG, ["u-bot"])

        assert set(found) == {"u-bot"}

    async def test_names_are_matched_whatever_the_case_of_unicode_letters(self) -> None:
        client = says(
            200, {"people": [{"user_id": "u-1", "email": "ÄDA@acme.test", "name": "Äda"}]}
        ).client()

        found = await client.resolve(ORG, ["ÄDA@acme.test"])
        again = await client.resolve(ORG, ["äda@acme.test"])

        assert set(found) == {"u-1", "äda@acme.test"}
        assert again == found
        assert len(cast(Asked, client._tokens).calls) == 1


class TestTheCache:
    async def test_it_is_fresh_at_exactly_thirty_seconds_and_stale_just_after(self) -> None:
        clock = ManualClock()
        asked = Asked(echoing_members)
        client = asked.client(clock)

        await client.resolve(ORG, ["u-1"])
        clock.advance(DirectoryClient.TTL)
        await client.resolve(ORG, ["u-1"])
        assert len(asked.calls) == 1
        clock.advance(0.5)
        await client.resolve(ORG, ["u-1"])

        assert len(asked.calls) == 2

    async def test_a_changed_name_shows_after_the_cache_runs_out(self) -> None:
        clock = ManualClock()
        names = iter(["Before", "After"])
        asked = Asked(
            lambda *_: httpx.Response(
                200, json={"people": [{"user_id": "u-1", "name": next(names)}]}
            )
        )
        client = asked.client(clock)

        before = await client.resolve(ORG, ["u-1"])
        clock.advance(31)
        after = await client.resolve(ORG, ["u-1"])

        assert (before["u-1"].name, after["u-1"].name) == ("Before", "After")

    async def test_the_same_identity_in_two_organisations_is_asked_in_each(self) -> None:
        asked = Asked(echoing_members)
        client = asked.client()

        await client.resolve("org-a", ["u-1"])
        await client.resolve("org-b", ["u-1"])
        await client.resolve("org-a", ["u-1"])

        assert [org for _, _, org, _ in asked.calls] == ["org-a", "org-b"]

    async def test_forgetting_makes_the_next_resolve_ask_again(self) -> None:
        asked = Asked(echoing_members)
        client = asked.client()

        await client.resolve(ORG, ["u-1"])
        client.forget()
        await client.resolve(ORG, ["u-1"])

        assert len(asked.calls) == 2

    async def test_a_person_looked_up_is_served_to_the_next_resolve_by_id_and_address(
        self,
    ) -> None:
        asked = Asked(lambda *_: httpx.Response(200, json=member("u-1")))
        client = asked.client()

        looked_up = await client.person(ORG, "u-1")
        by_id = await client.resolve(ORG, ["u-1"])
        by_address = await client.resolve(ORG, ["U-1@acme.test"])

        assert looked_up is not None
        assert by_id["u-1"] is looked_up and by_address["u-1@acme.test"] is looked_up
        assert len(asked.calls) == 1

    async def test_a_person_igni_does_not_know_is_not_remembered(self) -> None:
        asked = Asked(echoing_members)
        asked.answer = lambda m, p, kw: (
            httpx.Response(404) if m == "GET" else echoing_members(m, p, kw)
        )
        client = asked.client()

        assert await client.person(ORG, "u-1") is None
        assert set(await client.resolve(ORG, ["u-1"])) == {"u-1", "u-1@acme.test"}


class TestAMember:
    @pytest.mark.parametrize(
        ("status", "active"), [("active", True), ("deactivated", False), ("", False)]
    )
    def test_only_the_active_are_members_still(self, status: str, active: bool) -> None:
        assert Member(user_id="u", status=status).is_active is active

    def test_the_name_shows_or_else_the_address(self) -> None:
        assert Member(user_id="u", name="Ada", email="a@x").display_name == "Ada"
        assert Member(user_id="u", name="", email="a@x").display_name == "a@x"
        assert Member(user_id="u").display_name == ""


class TestTheBoundDirectory:
    async def test_it_asks_for_its_own_organisation_in_every_call(self) -> None:
        asked = Asked(
            lambda method, path, kwargs: httpx.Response(
                200,
                json={"org_id": "x", "people": []} if "organisation" in path else {"people": []},
            )
        )
        directory = Directory(asked.client(), "org-b")

        await directory.organisation()
        await directory.members()
        await directory.resolve(["u"])

        assert directory.org_id == "org-b"
        assert [org for _, _, org, _ in asked.calls] == ["org-b"] * 3
