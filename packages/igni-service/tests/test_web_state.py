"""The callback's state is compared with the login cookie whatever characters it holds."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from igni_service import IgniService
from igni_service.testing import FakeIgni, SettingsOverrides

SERVICE = "https://service.test"


@pytest.fixture
async def browser(fake: FakeIgni) -> AsyncIterator[httpx.AsyncClient]:
    igni: IgniService = fake.service(fake.settings(SettingsOverrides(public_base_url=SERVICE)))
    app = FastAPI()
    app.include_router(igni.web.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=SERVICE
    ) as client:
        yield client


@pytest.mark.parametrize("state", ["st\u00e4te", "\u65e5\u672c", "\U0001f511"])
async def test_a_state_with_characters_beyond_ascii_is_refused_not_a_crash(
    browser: httpx.AsyncClient, state: str
) -> None:
    browser.cookies.set("igni_login", "plain", domain="service.test", path="/auth")

    refused = await browser.get("/auth/callback", params={"code": "c", "state": state})

    assert refused.status_code == 400
    assert "not started here" in refused.text
