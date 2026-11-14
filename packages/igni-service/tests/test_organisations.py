"""igni telling the service that an organisation was deleted."""

from __future__ import annotations

import httpx

from igni_service import IgniService
from igni_service.testing import FakeIgni, TokenOverrides

from .conftest import ORG, OTHER_ORG, bearer


async def test_a_deleted_organisation_reaches_the_handler_with_its_id(
    igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient
) -> None:
    deleted: list[str] = []

    @igni.on_organisation_deleted
    async def organisation_deleted(org_id: str) -> None:
        deleted.append(org_id)

    response = await fake.directory.delete_organisation(ORG, fake.signer.igni_token(ORG)).send(http)

    assert response.status_code == 204
    assert deleted == [ORG]
    assert ORG not in fake.directory.organisations


async def test_telling_it_again_is_confirmed_again(
    igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient
) -> None:
    deleted: list[str] = []

    @igni.on_organisation_deleted
    async def organisation_deleted(org_id: str) -> None:
        deleted.append(org_id)

    deletion = fake.directory.delete_organisation(ORG, fake.signer.igni_token(ORG))
    first = await deletion.send(http)
    second = await deletion.send(http)

    assert (first.status_code, second.status_code) == (204, 204)
    assert deleted == [ORG, ORG]


async def test_a_token_for_one_organisation_cannot_delete_another(
    igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient
) -> None:
    @igni.on_organisation_deleted
    async def organisation_deleted(org_id: str) -> None:
        raise AssertionError("must not be reached")

    response = await http.delete(
        f"/v1/igni/organisations/{OTHER_ORG}", headers=bearer(fake.signer.igni_token(ORG))
    )

    assert response.status_code == 403


async def test_only_igni_may_call_and_only_with_a_token_for_this_service(
    igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient
) -> None:
    @igni.on_organisation_deleted
    async def organisation_deleted(org_id: str) -> None:
        raise AssertionError("must not be reached")

    for token in (
        fake.signer.person_token("u-ada", org_id=ORG),
        fake.signer.igni_token(ORG, TokenOverrides(aud="http://another-service.test")),
        fake.signer.igni_token(ORG, TokenOverrides(sub="https://not-igni.test")),
    ):
        response = await http.delete(f"/v1/igni/organisations/{ORG}", headers=bearer(token))
        assert response.status_code == 401
    assert (await http.delete(f"/v1/igni/organisations/{ORG}")).status_code == 401


async def test_a_service_without_a_handler_does_not_confirm(
    fake: FakeIgni, http: httpx.AsyncClient
) -> None:
    response = await fake.directory.delete_organisation(ORG, fake.signer.igni_token(ORG)).send(http)

    assert response.status_code == 501


def test_registering_a_handler_hands_it_back_unchanged() -> None:
    from igni_service.organisations import OrganisationHandlers

    handlers = OrganisationHandlers()

    async def gone(org_id: str) -> None:
        return None

    assert handlers.on_deleted(gone) is gone
    assert handlers.deleted is gone


async def test_a_second_handler_replaces_the_first(
    igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient
) -> None:
    told: list[str] = []

    @igni.on_organisation_deleted
    async def first(org_id: str) -> None:
        told.append(f"first {org_id}")

    @igni.on_organisation_deleted
    async def second(org_id: str) -> None:
        told.append(f"second {org_id}")

    await fake.directory.delete_organisation(ORG, fake.signer.igni_token(ORG)).send(http)

    assert told == [f"second {ORG}"]


async def test_a_handler_that_fails_does_not_confirm(igni: IgniService, fake: FakeIgni) -> None:
    @igni.on_organisation_deleted
    async def broken(org_id: str) -> None:
        raise RuntimeError("database down")

    from fastapi import FastAPI

    app = FastAPI(lifespan=igni.lifespan)
    igni.install(app)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://service.test") as client:
        response = await fake.directory.delete_organisation(ORG, fake.signer.igni_token(ORG)).send(
            client
        )

    assert response.status_code == 500
