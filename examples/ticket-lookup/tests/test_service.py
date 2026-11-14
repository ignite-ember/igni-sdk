"""The example's service, driven through its routes as igni and its people call them."""

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "service"))

from igni_service import IgniService, IgniUnavailable, Member  # noqa: E402
from igni_service.testing import FakeIgni, IgniAddresses  # noqa: E402

pytestmark = pytest.mark.anyio

EXTENSION = HERE.parent / "extension"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Tickets:
    """The service under test, its fake igni and a client that reaches it."""

    def __init__(self, fake: FakeIgni, igni: IgniService, http: httpx.AsyncClient) -> None:
        self.fake = fake
        self.igni = igni
        self.http = http

    def person(self, user_id: str, org_id: str = "org-1") -> dict[str, str]:
        token = self.fake.signer.person_token(user_id, org_id=org_id)
        return {"Authorization": f"Bearer {token}"}

    def igni_call(self, org_id: str = "org-1") -> dict[str, str]:
        return {"Authorization": f"Bearer {self.fake.signer.igni_token(org_id)}"}

    async def lookup(self, ticket: str, user_id: str, org_id: str = "org-1") -> httpx.Response:
        return await self.http.get(f"/v1/tickets/{ticket}", headers=self.person(user_id, org_id))

    async def export(self, user_id: str, org_id: str = "org-1") -> list[dict]:
        r = await self.http.get(
            f"/v1/igni/subjects/{user_id}/export", headers=self.igni_call(org_id)
        )
        assert r.status_code == 200, r.text
        return r.json()["sections"]

    async def erase(self, user_id: str, org_id: str = "org-1") -> None:
        r = await self.http.delete(f"/v1/igni/subjects/{user_id}", headers=self.igni_call(org_id))
        assert r.status_code in (200, 204), r.text


@pytest.fixture
async def tickets() -> AsyncIterator[Tickets]:
    from service import create_app

    fake = FakeIgni(addresses=IgniAddresses(service_url="http://tickets.test"))
    for org in ("org-1", "org-2"):
        fake.directory.add_member(org, Member(user_id="u-ada", email=f"ada@{org}.test"))
        fake.directory.add_member(org, Member(user_id="u-grace", email=f"grace@{org}.test"))
        fake.directory.add_member(
            org, Member(user_id="u-admin", email=f"admin@{org}.test", role="admin")
        )
    igni = fake.service()
    app = create_app(igni)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tickets.test") as http:
        yield Tickets(fake, igni, http)


async def test_a_lookup_is_exported_as_one_section_of_rows_in_order(tickets: Tickets) -> None:
    await tickets.lookup("T-1", "u-ada")
    await tickets.lookup("T-2", "u-ada")

    [section] = await tickets.export("u-ada")

    assert section["name"] == "Ticket lookups"
    assert section["rows"] == [{"ticket": "T-1"}, {"ticket": "T-2"}]


async def test_a_subject_with_no_lookups_exports_an_empty_section_and_erases_quietly(
    tickets: Tickets,
) -> None:
    assert await tickets.export("u-nobody") == [{"name": "Ticket lookups", "rows": []}]

    await tickets.erase("u-nobody")


async def test_a_repeated_lookup_is_kept_each_time(tickets: Tickets) -> None:
    await tickets.lookup("T-1", "u-ada")
    await tickets.lookup("T-1", "u-ada")

    [section] = await tickets.export("u-ada")

    assert section["rows"] == [{"ticket": "T-1"}, {"ticket": "T-1"}]


async def test_lookups_are_kept_per_org_and_per_user(tickets: Tickets) -> None:
    await tickets.lookup("T-ada-1", "u-ada", "org-1")
    await tickets.lookup("T-ada-2", "u-ada", "org-2")
    await tickets.lookup("T-grace", "u-grace", "org-1")

    assert (await tickets.export("u-ada", "org-1"))[0]["rows"] == [{"ticket": "T-ada-1"}]
    assert (await tickets.export("u-ada", "org-2"))[0]["rows"] == [{"ticket": "T-ada-2"}]
    assert (await tickets.export("u-grace", "org-1"))[0]["rows"] == [{"ticket": "T-grace"}]


async def test_erasing_one_subject_leaves_everyone_elses_lookups(tickets: Tickets) -> None:
    await tickets.lookup("T-ada-1", "u-ada", "org-1")
    await tickets.lookup("T-ada-2", "u-ada", "org-2")
    await tickets.lookup("T-grace", "u-grace", "org-1")

    await tickets.erase("u-ada", "org-1")

    assert (await tickets.export("u-ada", "org-1"))[0]["rows"] == []
    assert (await tickets.export("u-ada", "org-2"))[0]["rows"] == [{"ticket": "T-ada-2"}]
    assert (await tickets.export("u-grace", "org-1"))[0]["rows"] == [{"ticket": "T-grace"}]


async def test_a_ticket_id_is_stored_as_it_came(tickets: Tickets) -> None:
    odd = "T-%C3%A9%20" + "x" * 500
    r = await tickets.lookup(odd, "u-ada")
    assert r.status_code == 200
    assert r.json()["id"] == "T-é " + "x" * 500

    [section] = await tickets.export("u-ada")
    assert section["rows"] == [{"ticket": "T-é " + "x" * 500}]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-token"}])
async def test_a_lookup_without_a_good_token_is_refused_and_recorded_nowhere(
    tickets: Tickets, headers: dict[str, str]
) -> None:
    r = await tickets.http.get("/v1/tickets/T-1", headers=headers)

    assert r.status_code == 401
    assert (await tickets.export("u-ada"))[0]["rows"] == []


async def test_the_vm_profile_is_for_an_org_admin(tickets: Tickets) -> None:
    anonymous = await tickets.http.get("/v1/vm-profile")
    member = await tickets.http.get("/v1/vm-profile", headers=tickets.person("u-ada"))

    assert anonymous.status_code == 401
    assert member.status_code == 403


async def test_an_admin_reads_what_became_of_the_extensions_vm_request_in_their_org(
    tickets: Tickets,
) -> None:
    await tickets.fake.upload(EXTENSION, tickets.igni)

    r = await tickets.http.get("/v1/vm-profile", headers=tickets.person("u-admin", "org-2"))

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["org_id"] == "org-2"
    assert body["extension_id"] == "acme.tickets"
    assert body["request"]["state"] == "pending"
    assert body["request"]["requested"]["memory_mib"] == 2048
    assert body["request"]["requested"]["packages"]["apt"] == ["jq"]
    assert body["profile"] is None


async def test_a_host_that_cannot_answer_is_a_server_error(tickets: Tickets) -> None:
    tickets.fake.traffic.fail("/v1/service-vm-profile", 503)

    with pytest.raises(IgniUnavailable):
        await tickets.http.get("/v1/vm-profile", headers=tickets.person("u-admin"))
