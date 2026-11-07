"""Gaps the first real service found, closed in the SDK rather than worked around.

Artifacts checks a token from a WebSocket greeting (no header), serves
public links that do more for somebody signed in, and shares one fake
igni across a test session.
"""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from fastapi import Depends, FastAPI

from igni_service import IgniService, Member, Organisation, Person, TokenRefused
from igni_service.testing import FakeIgni, TokenOverrides
from igni_service.testing_sessions import HeldRefresh


@pytest.fixture
def fake() -> FakeIgni:
    fake = FakeIgni()
    fake.directory.add_organisation(Organisation(org_id="org-1", name="Acme"))
    fake.directory.add_member("org-1", Member(user_id="u-1", email="ada@acme.com", name="Ada"))
    return fake


@pytest.fixture
def igni(fake: FakeIgni) -> IgniService:
    return fake.service()


async def test_a_bare_token_names_its_person(fake: FakeIgni, igni: IgniService) -> None:
    person = await igni.person_of(fake.signer.person_token("u-1", org_id="org-1"))

    assert (person.user_id, person.org_id) == ("u-1", "org-1")


async def test_a_bare_token_is_refused_without_an_http_error(igni: IgniService) -> None:
    with pytest.raises(TokenRefused):
        await igni.person_of("not-a-token")


async def test_signing_in_is_optional_but_a_bad_token_is_not(
    fake: FakeIgni, igni: IgniService
) -> None:
    app = FastAPI()

    @app.get("/read")
    async def read(person: Person | None = Depends(igni.optional_person)) -> dict[str, str]:
        return {"who": person.user_id if person else "anybody"}

    signed_in = {"Authorization": f"Bearer {fake.signer.person_token('u-1', org_id='org-1')}"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://service") as client:
        assert (await client.get("/read")).json() == {"who": "anybody"}
        assert (await client.get("/read", headers=signed_in)).json() == {"who": "u-1"}
        broken = await client.get("/read", headers={"Authorization": "Bearer broken"})
        assert broken.status_code == 401


async def test_a_token_lifetime_may_be_a_duration(fake: FakeIgni, igni: IgniService) -> None:
    token = fake.signer.person_token(
        "u-1", org_id="org-1", overrides=TokenOverrides(lifetime=timedelta(minutes=5))
    )

    assert (await igni.person_of(token)).user_id == "u-1"


def test_reset_forgets_what_happened_and_keeps_who_exists(fake: FakeIgni) -> None:
    fake.traffic.fail("/v1/directory", 503)
    fake.oauth.grants.append("client_credentials")
    fake.oauth.revoked.append("refresh-1")
    fake.oauth.sign_ins.refresh["refresh-1"] = HeldRefresh(
        client_id="c-1", user_id="u-1", org_id="org-1", grant="g-1"
    )
    fake.revocations.publish("u-1", org_id="org-1")
    fake.extensions.hold("it asks for more")
    fake.reset()

    assert fake.traffic.failing == {}
    assert fake.oauth.grants == []
    assert fake.oauth.revoked == []
    assert fake.oauth.sign_ins.refresh == {}
    assert fake.oauth.sign_ins.codes == {}
    assert fake.notifications.deliveries == []
    assert fake.revocations.revocations == [], "a revocation is something that happened"
    assert fake.extensions.hold_uploads is None
    assert fake.extensions.held == {}
    assert "u-1" in fake.directory.organisations["org-1"].members
