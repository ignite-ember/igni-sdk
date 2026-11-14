"""The fake's directory: its organisations, how it searches and finds members, its routes.

Driven at the directory itself, so the search order, the limit and the
claims are seen as igni's directory answers them.
"""

from __future__ import annotations

import json

import httpx
import pytest

from igni_service.directory import Member, Organisation
from igni_service.testing_bearers import TokenHolder
from igni_service.testing_directory import (
    MAX_PEOPLE,
    FakeDirectory,
    FakeOrganisation,
    MemberQuery,
)
from igni_service.testing_wire import DetailError, RoutedCall, SeenRequest
from igni_service.urls import IgniPaths

ORG = "org-acme"


def asked(**query: str) -> SeenRequest:
    return SeenRequest(
        method="GET",
        path=f"{IgniPaths.DIRECTORY}/members",
        headers={},
        body=b"",
        query={name: [value] for name, value in query.items()},
    )


def query_of(**query: str) -> MemberQuery:
    parsed = MemberQuery.from_request(asked(**query))
    assert isinstance(parsed, MemberQuery)
    return parsed


def routed(path: str, *, org: str = ORG, body: bytes = b"", **query: str) -> RoutedCall:
    seen = asked(**query).model_copy(update={"path": f"{IgniPaths.DIRECTORY}{path}", "body": body})
    return RoutedCall(seen=seen, holder=TokenHolder(client_id="c-1", org_id=org))


def organisation_with(*members: Member) -> FakeOrganisation:
    held = FakeOrganisation(organisation=Organisation(org_id=ORG, name="Acme"))
    for member in members:
        held.members[member.user_id] = member
    return held


def ids(people: list[Member]) -> list[str]:
    return [m.user_id for m in people]


# ── The query ───────────────────────────────────────────────────────


def test_a_query_without_parameters_asks_for_a_hundred_active_members() -> None:
    assert query_of() == MemberQuery(query="", limit=100, include_former=False)


def test_the_query_is_casefolded_and_former_members_are_wanted_only_for_true() -> None:
    assert query_of(query="ADA").query == "ada"
    assert query_of(include_former="true").include_former is True
    assert query_of(include_former="True").include_former is False
    assert query_of(include_former="1").include_former is False


def test_a_limit_above_what_igni_answers_is_cut_to_it() -> None:
    assert MAX_PEOPLE == 500
    assert query_of(limit="500").limit == 500
    assert query_of(limit="501").limit == 500
    assert query_of(limit="100000").limit == 500


@pytest.mark.parametrize("limit", ["many", "1.5", "", "-", "1e3", " 7"])
def test_a_limit_that_is_not_a_whole_number_is_refused_with_its_value(limit: str) -> None:
    refused = MemberQuery.from_request(asked(limit=limit))

    assert isinstance(refused, DetailError)
    assert (refused.status, refused.detail) == (422, f"limit must be a whole number, not {limit!r}")


@pytest.mark.parametrize("limit", ["0", "-1", "-5"])
def test_a_limit_below_one_asks_for_one_as_the_sdk_does(limit: str) -> None:
    assert query_of(limit=limit).limit == 1


def test_a_negative_limit_answers_one_member_and_does_not_drop_the_last_ones() -> None:
    directory = FakeDirectory()
    for name in "abcdefg":
        directory.add_member(ORG, Member(user_id=f"u-{name}", email=f"{name}@acme.test"))

    answer = directory.route(routed("/members", limit="-5"))

    assert [p["user_id"] for p in answer.json()["people"]] == ["u-a"]


# ── Finding and searching ───────────────────────────────────────────


def test_find_takes_an_id_or_an_address_in_any_case_and_ignores_surrounding_space() -> None:
    ada = Member(user_id="U-Ada", email="Ada@Acme.test")
    held = organisation_with(ada)

    for identity in ("u-ada", "U-ADA", "ada@acme.test", "  ADA@acme.TEST \n", "\tU-Ada"):
        assert held.find(identity) == ada
    assert held.find("ada") is None
    assert held.find("") is None
    assert held.find("   ") is None


def test_find_never_matches_an_empty_identity_to_a_member_without_an_address() -> None:
    held = organisation_with(Member(user_id="u-x", email=""))

    assert held.find("") is None
    assert held.find("u-x") is not None


def test_search_matches_the_start_of_an_address_or_a_name_in_any_case() -> None:
    held = organisation_with(
        Member(user_id="u-1", email="zed@acme.test", name="Ada Lovelace"),
        Member(user_id="u-2", email="ada@acme.test", name="Zed"),
        Member(user_id="u-3", email="bob@acme.test", name="Robert Ada"),
    )

    found = held.search(query_of(query="ADA"))

    assert ids(found) == ["u-2", "u-1"]


def test_search_with_no_query_answers_every_active_member_sorted_by_address() -> None:
    held = organisation_with(
        Member(user_id="u-1", email="c@acme.test"),
        Member(user_id="u-2", email="a@acme.test"),
        Member(user_id="u-3", email="b@acme.test"),
    )

    assert ids(held.search(query_of())) == ["u-2", "u-3", "u-1"]


def test_search_cuts_to_the_limit_after_sorting() -> None:
    held = organisation_with(
        Member(user_id="u-1", email="c@acme.test"),
        Member(user_id="u-2", email="a@acme.test"),
        Member(user_id="u-3", email="b@acme.test"),
    )

    assert ids(held.search(query_of(limit="2"))) == ["u-2", "u-3"]


def test_search_leaves_former_members_out_unless_asked() -> None:
    held = organisation_with(
        Member(user_id="u-1", email="a@acme.test"),
        Member(user_id="u-2", email="b@acme.test", status="deactivated"),
    )

    assert ids(held.search(query_of())) == ["u-1"]
    assert ids(held.search(query_of(include_former="true"))) == ["u-1", "u-2"]


def test_deactivating_a_member_marks_them_and_an_unknown_one_raises() -> None:
    held = organisation_with(Member(user_id="u-1", email="a@acme.test"))

    held.deactivate("u-1")

    assert held.members["u-1"].status == "deactivated"
    assert not held.members["u-1"].is_active
    with pytest.raises(KeyError):
        held.deactivate("u-nobody")


# ── Claims and served ───────────────────────────────────────────────


def test_a_members_claims_carry_their_role_address_name_and_standing() -> None:
    held = organisation_with(
        Member(user_id="u-1", email="a@acme.test", name="Ada", role="admin", super_admin=True)
    )

    claims = held.claims_for("u-1")

    assert (claims.org, claims.org_name) == (ORG, "Acme")
    assert (claims.org_role, claims.email, claims.name, claims.super_admin) == (
        "admin",
        "a@acme.test",
        "Ada",
        True,
    )


def test_a_person_who_is_no_member_gets_the_bare_organisation_claims() -> None:
    claims = organisation_with().claims_for("u-stranger")

    assert (claims.org, claims.org_name) == (ORG, "Acme")
    assert (claims.org_role, claims.email, claims.name, claims.super_admin) == (
        "member",
        "",
        "",
        False,
    )


def test_an_organisation_the_directory_lacks_is_named_by_its_id() -> None:
    claims = FakeDirectory().claims_for("org-nowhere", "u-1")

    assert (claims.org, claims.org_name) == ("org-nowhere", "org-nowhere")
    assert FakeDirectory().member("org-nowhere", "u-1") is None
    assert FakeDirectory().is_member("org-nowhere", "u-1") is False


def test_the_directorys_claims_are_the_organisations_when_it_exists() -> None:
    directory = FakeDirectory()
    directory.add_organisation(Organisation(org_id=ORG, name="Acme"))
    directory.add_member(ORG, Member(user_id="u-1", email="a@acme.test", role="admin"))

    assert directory.claims_for(ORG, "u-1").org_role == "admin"
    assert directory.is_member(ORG, "A@ACME.test") is True
    assert directory.is_member(ORG, "u-2") is False


# ── Setting the scene ───────────────────────────────────────────────


def test_adding_a_member_makes_the_organisation_named_by_its_id() -> None:
    directory = FakeDirectory()

    directory.add_member("org-new", Member(user_id="u-1"))

    made = directory.organisations["org-new"].organisation
    assert (made.org_id, made.name, made.slug, made.tenant_number) == (
        "org-new",
        "org-new",
        "org-new",
        1,
    )
    assert directory.ensure("org-new") is directory.organisations["org-new"]


def test_adding_an_organisation_again_replaces_the_record_and_keeps_its_members() -> None:
    directory = FakeDirectory()
    directory.add_organisation(Organisation(org_id=ORG, name="Acme"))
    directory.add_member(ORG, Member(user_id="u-1"))

    directory.add_organisation(Organisation(org_id=ORG, name="Acme Ltd", tenant_number=9))

    held = directory.organisations[ORG]
    assert (held.organisation.name, held.organisation.tenant_number) == ("Acme Ltd", 9)
    assert list(held.members) == ["u-1"]


def test_a_deletion_removes_the_organisation_and_owes_the_call_with_igni_token() -> None:
    directory = FakeDirectory()
    directory.add_member(ORG, Member(user_id="u-1"))

    owed = directory.delete_organisation(ORG, "igni-token")

    assert ORG not in directory.organisations
    assert owed.org_id == ORG
    assert owed.path == f"{IgniPaths.ORGANISATIONS}/{ORG}"
    assert owed.headers == {"Authorization": "Bearer igni-token"}
    assert directory.route(routed("/organisation")).status_code == 404


def test_deleting_an_organisation_that_is_not_there_still_owes_the_call() -> None:
    owed = FakeDirectory().delete_organisation("org-nowhere", "t")

    assert owed.path == f"{IgniPaths.ORGANISATIONS}/org-nowhere"


async def test_the_owed_deletion_is_delivered_each_time_it_is_sent() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    owed = FakeDirectory().delete_organisation(ORG, "igni-token")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://service.test"
    ) as http:
        await owed.send(http)
        await owed.send(http)

    assert [(r.method, r.url.path, r.headers["authorization"]) for r in seen] == [
        ("DELETE", owed.path, "Bearer igni-token")
    ] * 2


# ── Routes ──────────────────────────────────────────────────────────


def test_the_served_organisations_are_all_of_them_whatever_the_token() -> None:
    directory = FakeDirectory()
    directory.add_organisation(Organisation(org_id="org-a", name="A"))
    directory.add_organisation(Organisation(org_id="org-b", name="B"))

    answer = directory.served(routed("", org=""))

    assert answer.status_code == 200
    assert answer.json() == {
        "organisations": [{"org_id": "org-a", "name": "A"}, {"org_id": "org-b", "name": "B"}]
    }


def test_a_token_for_an_unknown_organisation_is_told_so() -> None:
    answer = FakeDirectory().route(routed("/members", org="org-nowhere"))

    assert (answer.status_code, answer.json()) == (404, {"detail": "no such organisation"})


def test_the_organisation_route_answers_the_record() -> None:
    directory = FakeDirectory()
    directory.add_organisation(Organisation(org_id=ORG, name="Acme", slug="acme"))

    answer = directory.route(routed("/organisation"))

    assert answer.json()["slug"] == "acme"


def test_the_members_route_answers_the_search_and_a_bad_limit_with_422() -> None:
    directory = FakeDirectory()
    directory.add_member(ORG, Member(user_id="u-1", email="b@acme.test"))
    directory.add_member(ORG, Member(user_id="u-2", email="a@acme.test"))

    answer = directory.route(routed("/members", query="A"))
    refused = directory.route(routed("/members", limit="lots"))

    assert [p["user_id"] for p in answer.json()["people"]] == ["u-2"]
    assert refused.status_code == 422
    assert refused.json() == {"detail": "limit must be a whole number, not 'lots'"}


def test_resolve_answers_each_member_once_and_drops_the_unknown() -> None:
    directory = FakeDirectory()
    directory.add_member(ORG, Member(user_id="u-1", email="a@acme.test"))
    directory.add_member(ORG, Member(user_id="u-2", email="b@acme.test"))
    body = json.dumps({"identities": ["a@ACME.test", "u-1", "nobody", "u-2", ""]}).encode()

    answer = directory.route(routed("/people/resolve", body=body))

    assert [p["user_id"] for p in answer.json()["people"]] == ["u-1", "u-2"]


def test_resolve_with_no_identities_answers_nobody_and_a_bad_body_is_422() -> None:
    directory = FakeDirectory()
    directory.add_member(ORG, Member(user_id="u-1"))

    nobody = directory.route(routed("/people/resolve", body=b'{"identities": []}'))
    bad = directory.route(routed("/people/resolve", body=b"nonsense"))

    assert nobody.json() == {"people": []}
    assert bad.status_code == 422


def test_a_person_route_answers_the_member_by_id_only_and_others_are_not_found() -> None:
    directory = FakeDirectory()
    directory.add_member(ORG, Member(user_id="u-1", email="a@acme.test"))

    found = directory.route(routed("/people/u-1"))
    by_address = directory.route(routed("/people/a@acme.test"))
    empty = directory.route(routed("/people/"))
    other = directory.route(routed("/nothing"))

    assert found.json()["email"] == "a@acme.test"
    for answer in (by_address, empty):
        assert (answer.status_code, answer.json()) == (
            404,
            {"detail": "Not a member of this organisation"},
        )
    assert (other.status_code, other.json()) == (404, {"detail": "Not Found"})
