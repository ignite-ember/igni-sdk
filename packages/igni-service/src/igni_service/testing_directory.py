"""igni's directory, as the fake keeps it: organisations, their members, and its routes.

A test sets the scene with `add_organisation` and `add_member`, plays a
person leaving with `FakeOrganisation.deactivate`, and igni deleting an
organisation with `delete_organisation`, which hands back the call igni
owes the service. The routes answer what igni's directory answers a
service token for one organisation.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
from pydantic import BaseModel, ConfigDict, Field

from igni_service.directory import Member, Members, Organisation, ResolveRequest
from igni_service.revocations import ServedOrganisation, ServedOrganisations
from igni_service.testing_claims import PersonClaims
from igni_service.testing_wire import DetailError, RoutedCall, SeenRequest
from igni_service.urls import IgniPaths

MAX_PEOPLE = 500
"""The most people the directory answers in one call."""


class MemberQuery(BaseModel):
    """`GET /v1/directory/members`'s query, as igni reads it."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    query: str = ""
    limit: int = 100
    include_former: bool = False

    @classmethod
    def from_request(cls, seen: SeenRequest) -> MemberQuery | DetailError:
        """Read the query of a members request, or the 422 it is refused with.

        Args:
            seen: The request as the fake received it: its query holds what
                to look for, how many to answer, and whether former members
                are wanted.
        """
        limit = seen.first("limit", "100")
        if not limit.lstrip("-").isdigit():
            return DetailError(detail=f"limit must be a whole number, not {limit!r}", status=422)
        return cls(
            query=seen.first("query").casefold(),
            limit=max(1, min(int(limit), MAX_PEOPLE)),
            include_former=seen.first("include_former", "false") == "true",
        )


class FakeOrganisation(BaseModel):
    """One organisation in igni's directory, and its members by user id."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    organisation: Organisation
    members: dict[str, Member] = Field(default_factory=dict)

    def find(self, identity: str) -> Member | None:
        """The member a user id or an address names, either spelling, any case.

        Args:
            identity: The user id or the email address of the member to
                find, in any case.
        """
        wanted = identity.strip().casefold()
        return next(
            (
                m
                for m in self.members.values()
                if m.user_id.casefold() == wanted or (m.email and m.email.casefold() == wanted)
            ),
            None,
        )

    def search(self, query: MemberQuery) -> list[Member]:
        """Members whose address or name starts with the query, by address.

        Args:
            query: What to look for: the text to match at the start of an
                address or a name, how many to answer, and whether former
                members are among them.
        """
        people = sorted(
            (
                m
                for m in self.members.values()
                if (query.include_former or m.is_active)
                and (
                    not query.query
                    or m.email.casefold().startswith(query.query)
                    or m.name.casefold().startswith(query.query)
                )
            ),
            key=lambda m: m.email,
        )
        return people[: query.limit]

    def deactivate(self, user_id: str) -> None:
        """Somebody leaves: their refresh tokens stop working at once.

        Args:
            user_id: The id of the member who leaves.
        """
        self.members[user_id] = self.members[user_id].model_copy(update={"status": "deactivated"})

    def claims_for(self, user_id: str) -> PersonClaims:
        """What a token for `user_id` in this organisation says about them.

        Args:
            user_id: The id of the member the token is for: whose claims
                these are.
        """
        member = self.members.get(user_id)
        claims = PersonClaims(org=self.organisation.org_id, org_name=self.organisation.name)
        if member is None:
            return claims
        return claims.model_copy(
            update={
                "org_role": member.role,
                "email": member.email,
                "name": member.name,
                "super_admin": member.super_admin,
            }
        )

    def served(self) -> ServedOrganisation:
        return ServedOrganisation(org_id=self.organisation.org_id, name=self.organisation.name)


class OrganisationDeletion(BaseModel):
    """What igni sends a service when it deletes an organisation."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    org_id: str
    """The organisation igni deleted."""
    path: str
    """The service's route igni calls: `/v1/igni/organisations/<org_id>`."""
    headers: dict[str, str]
    """igni's headers, its own token among them."""

    async def send(self, http: httpx.AsyncClient) -> httpx.Response:
        """Deliver it to the service `http` reaches, as igni does — again, if called again.

        Args:
            http: The client that reaches the service: the deletion is sent
                through it, to the service's own route.
        """
        return await http.delete(self.path, headers=self.headers)


OrgHandler = Callable[[FakeOrganisation, SeenRequest], httpx.Response]


class FakeDirectory:
    """Every organisation igni knows, by id."""

    def __init__(self) -> None:
        self.organisations: dict[str, FakeOrganisation] = {}
        self._routes: dict[str, OrgHandler] = {
            "/organisation": self._organisation,
            "/members": self._members,
            "/people/resolve": self._resolve,
        }

    # ── Setting the scene ───────────────────────────────────────────

    def add_organisation(self, organisation: Organisation) -> Organisation:
        """Add `organisation`, or replace what igni knows about it, keeping its members.

        Args:
            organisation: The organisation as igni's directory knows it.
        """
        held = self.organisations.get(organisation.org_id)
        if held is None:
            self.organisations[organisation.org_id] = FakeOrganisation(organisation=organisation)
        else:
            held.organisation = organisation
        return organisation

    def ensure(self, org_id: str) -> FakeOrganisation:
        """The organisation `org_id`, made with its id for its name and slug if it is new.

        Args:
            org_id: The id of the organisation: which one is wanted.
        """
        if org_id not in self.organisations:
            self.add_organisation(
                Organisation(org_id=org_id, name=org_id, slug=org_id, tenant_number=1)
            )
        return self.organisations[org_id]

    def add_member(self, org_id: str, member: Member) -> Member:
        """Put `member` in the organisation `org_id`.

        Args:
            org_id: The id of the organisation the member belongs to.
            member: The member to add: their user id is how they are found.
        """
        self.ensure(org_id).members[member.user_id] = member
        return member

    def delete_organisation(self, org_id: str, igni_token: str) -> OrganisationDeletion:
        """Delete an organisation, as igni does: it leaves the directory,
        and the service is owed the call that says so, carrying `igni_token`.

        `await fake.directory.delete_organisation(ORG, token).send(http)` delivers it.

        Args:
            org_id: The id of the organisation igni deletes: which one
                leaves the directory.
            igni_token: The token igni calls the service with: the bearer
                token of that call.
        """
        self.organisations.pop(org_id, None)
        return OrganisationDeletion(
            org_id=org_id,
            path=f"{IgniPaths.ORGANISATIONS}/{org_id}",
            headers={"Authorization": f"Bearer {igni_token}"},
        )

    # ── Asking it ───────────────────────────────────────────────────

    def member(self, org_id: str, identity: str) -> Member | None:
        """The member `identity` names in `org_id`.

        Args:
            org_id: The id of the organisation the member is looked for in.
            identity: The user id or the email address of the member to
                find, in any case.
        """
        held = self.organisations.get(org_id)
        return held.find(identity) if held else None

    def is_member(self, org_id: str, user_id: str) -> bool:
        """Whether `user_id` is a member of `org_id`.

        Args:
            org_id: The id of the organisation the person is looked for in.
            user_id: The id of the person: whether they belong to it.
        """
        return self.member(org_id, user_id) is not None

    def claims_for(self, org_id: str, user_id: str) -> PersonClaims:
        """A person's claims in `org_id`; an organisation igni lacks is named by its id.

        Args:
            org_id: The id of the organisation the token is for.
            user_id: The id of the member the token is about.
        """
        held = self.organisations.get(org_id)
        return held.claims_for(user_id) if held else PersonClaims(org=org_id, org_name=org_id)

    # ── Routes ──────────────────────────────────────────────────────

    def served(self, call: RoutedCall) -> httpx.Response:
        """`GET /v1/organisations/served`: every organisation, for a token for none.

        Args:
            call: The request as it was routed: every organisation is
                answered for it, whoever it was for.
        """
        served = ServedOrganisations(
            organisations=[o.served() for o in self.organisations.values()]
        )
        return httpx.Response(200, json=served.model_dump())

    def route(self, call: RoutedCall) -> httpx.Response:
        """`/v1/directory/...` for the organisation the service token is for.

        Args:
            call: The request as it was routed: its path says what is asked
                for, and the token's organisation is whose directory answers.
        """
        held = self.organisations.get(call.holder.org_id)
        if held is None:
            return DetailError(detail="no such organisation", status=404).to_response()
        suffix = call.seen.path.removeprefix(IgniPaths.DIRECTORY)
        handler = self._routes.get(suffix)
        if handler is not None:
            return handler(held, call.seen)
        if suffix.startswith("/people/"):
            return self._person(held, suffix.removeprefix("/people/"))
        return DetailError(detail="Not Found", status=404).to_response()

    @staticmethod
    def _organisation(held: FakeOrganisation, seen: SeenRequest) -> httpx.Response:
        return httpx.Response(200, json=held.organisation.model_dump())

    @staticmethod
    def _members(held: FakeOrganisation, seen: SeenRequest) -> httpx.Response:
        query = MemberQuery.from_request(seen)
        if isinstance(query, DetailError):
            return query.to_response()
        return httpx.Response(200, json=Members(people=held.search(query)).model_dump())

    @staticmethod
    def _resolve(held: FakeOrganisation, seen: SeenRequest) -> httpx.Response:
        wanted = seen.json_model(ResolveRequest)
        if isinstance(wanted, DetailError):
            return wanted.to_response()
        found: dict[str, Member] = {}
        for identity in wanted.identities:
            member = held.find(identity)
            if member is not None:
                found[member.user_id] = member
        return httpx.Response(200, json=Members(people=list(found.values())).model_dump())

    @staticmethod
    def _person(held: FakeOrganisation, user_id: str) -> httpx.Response:
        member = held.members.get(user_id)
        if member is None:
            return DetailError(detail="Not a member of this organisation", status=404).to_response()
        return httpx.Response(200, json=member.model_dump())


__all__ = ["FakeDirectory", "FakeOrganisation", "MemberQuery", "OrganisationDeletion"]
