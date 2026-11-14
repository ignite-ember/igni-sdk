"""The routes `igni.web.router` mounts: which paths, which methods, and that none is in the schema."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute

from igni_service.testing import FakeIgni


def test_the_router_mounts_login_and_callback_for_get_and_logout_for_get_and_post(
    fake: FakeIgni,
) -> None:
    web = fake.service().web

    routes = {r.path: set(r.methods or ()) for r in web.router.routes if isinstance(r, APIRoute)}

    assert routes == {
        "/auth/login": {"GET"},
        "/auth/callback": {"GET"},
        "/auth/logout": {"GET", "POST"},
    }
    assert (web.login_path, web.logout_path) == ("/auth/login", "/auth/logout")


def test_the_router_is_built_once_and_keeps_its_routes_out_of_the_schema(fake: FakeIgni) -> None:
    web = fake.service().web
    app = FastAPI()
    app.include_router(web.router)

    assert web.router is web.router
    assert app.openapi()["paths"] == {}
