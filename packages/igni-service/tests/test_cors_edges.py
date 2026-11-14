"""The edges of cross-origin answers: what is not a preflight, what is not a token, what is kept."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import Response, StreamingResponse
from starlette.routing import Mount
from starlette.types import Message, Receive, Scope, Send

from igni_service import IgniService, Person
from igni_service.cors import BearerCors, BearerRoutes
from igni_service.testing import FakeIgni

from .conftest import ORG, bearer
from .test_cors import PAGE_ORIGIN, preflight
from .test_cors import cors_app as cors_app  # noqa: F401 — the fixture
from .test_cors import page as page  # noqa: F401 — the fixture


def token_of(fake: FakeIgni) -> str:
    return fake.signer.person_token("u-max", org_id=ORG)


@pytest.fixture
def credentialed_app(igni: IgniService) -> FastAPI:
    app = FastAPI()
    igni.install(app)

    @app.get("/v1/credentialed")
    async def credentialed(person: Person = Depends(igni.person)) -> Response:
        return Response("ok", headers={"Access-Control-Allow-Credentials": "true", "X-Own": "kept"})

    @app.get("/v1/stream")
    async def stream(person: Person = Depends(igni.person)) -> StreamingResponse:
        async def chunks() -> Any:
            yield b"one,"
            yield b"two"

        return StreamingResponse(chunks(), media_type="text/plain")

    return app


@pytest.fixture
async def credentialed(credentialed_app: FastAPI) -> Any:
    transport = httpx.ASGITransport(app=credentialed_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://service.test", headers={"Origin": PAGE_ORIGIN}
    ) as client:
        yield client


class TestTheAnswerToABearerCall:
    async def test_it_exposes_every_header_and_allows_every_origin(
        self, page: httpx.AsyncClient, fake: FakeIgni
    ) -> None:
        response = await page.get("/v1/notes", headers=bearer(token_of(fake)))

        assert response.headers["access-control-allow-origin"] == "*"
        assert response.headers["access-control-expose-headers"] == "*"

    async def test_a_credentials_yes_the_handler_set_is_taken_back_and_its_other_headers_kept(
        self, credentialed: httpx.AsyncClient, fake: FakeIgni
    ) -> None:
        response = await credentialed.get("/v1/credentialed", headers=bearer(token_of(fake)))

        assert "access-control-allow-credentials" not in response.headers
        assert response.headers["x-own"] == "kept"
        assert response.headers["access-control-allow-origin"] == "*"

    async def test_a_streamed_answer_is_readable_and_whole(
        self, credentialed: httpx.AsyncClient, fake: FakeIgni
    ) -> None:
        response = await credentialed.get("/v1/stream", headers=bearer(token_of(fake)))

        assert response.text == "one,two"
        assert response.headers["access-control-allow-origin"] == "*"

    @pytest.mark.parametrize("scheme", ["bearer", "BEARER", "Bearer"])
    async def test_the_scheme_is_matched_in_any_case(
        self, page: httpx.AsyncClient, fake: FakeIgni, scheme: str
    ) -> None:
        response = await page.get(
            "/v1/notes", headers={"Authorization": f"{scheme} {token_of(fake)}"}
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "*"

    @pytest.mark.parametrize(
        "value", ["Bearer", "Bearer ", "Bearer    ", "Basic dXNlcjpwdw==", "x"]
    )
    async def test_an_empty_token_or_another_scheme_gets_no_yes(
        self, page: httpx.AsyncClient, value: str
    ) -> None:
        response = await page.get("/v1/public", headers={"Authorization": value})

        assert "access-control-allow-origin" not in response.headers
        assert "access-control-expose-headers" not in response.headers


class TestWhatIsNotAPreflight:
    async def test_an_options_without_a_requested_method_goes_to_the_app(
        self, page: httpx.AsyncClient
    ) -> None:
        response = await page.options("/v1/notes")

        assert response.status_code == 405
        assert "access-control-allow-origin" not in response.headers

    async def test_an_options_without_an_origin_goes_to_the_app_whatever_it_asks(
        self, cors_app: FastAPI
    ) -> None:
        transport = httpx.ASGITransport(app=cors_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://service.test") as plain:
            response = await plain.options("/v1/notes", headers=preflight("GET"))

        assert response.status_code == 405
        assert "access-control-allow-origin" not in response.headers

    async def test_a_scope_that_is_not_http_goes_to_the_app_untouched(
        self, igni: IgniService
    ) -> None:
        seen: list[Scope] = []

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            seen.append(scope)

        cors = BearerCors(app, igni=igni)
        for kind in ("lifespan", "websocket"):
            scope = {"type": kind, "headers": [(b"origin", PAGE_ORIGIN.encode())]}
            await cors(scope, _never_received, _never_sent)

        assert [s["type"] for s in seen] == ["lifespan", "websocket"]


class TestThePreflight:
    @pytest.mark.parametrize("method", ["get", "Post", "delete"])
    async def test_the_requested_method_is_matched_in_any_case(
        self, page: httpx.AsyncClient, method: str
    ) -> None:
        response = await page.options("/v1/notes", headers=preflight(method))

        assert response.status_code == 204

    @pytest.mark.parametrize(
        "asked",
        ["Authorization", "AUTHORIZATION, Content-Type", " authorization , content-type ,"],
    )
    async def test_the_requested_headers_are_matched_in_any_case_and_spacing(
        self, page: httpx.AsyncClient, asked: str
    ) -> None:
        response = await page.options("/v1/notes", headers=preflight("GET", asked))

        assert response.status_code == 204
        assert response.headers["access-control-max-age"] == "600"

    @pytest.mark.parametrize(
        "asked", ["", " , ", "content-type", "x-other", "authorization,x-other"]
    )
    async def test_a_preflight_that_does_not_ask_for_authorization_alone_is_refused(
        self, page: httpx.AsyncClient, asked: str
    ) -> None:
        response = await page.options("/v1/notes", headers=preflight("GET", asked))

        assert response.status_code == 403
        assert response.text == "Cross-origin calls carry a bearer token and nothing else"
        assert "access-control-allow-origin" not in response.headers

    @pytest.mark.parametrize("method", ["TRACE", "CONNECT", "TRIGGER", "OPTIONS", ""])
    async def test_a_method_that_is_not_allowed_is_refused(
        self, page: httpx.AsyncClient, method: str
    ) -> None:
        assert (await page.options("/v1/notes", headers=preflight(method))).status_code == 403

    @pytest.mark.parametrize(
        "path", ["/auth", "/auth/", "/v1/igni/subjects", "/v1/igni/organisations"]
    )
    async def test_the_closed_prefixes_are_closed_with_or_without_the_slash(
        self, page: httpx.AsyncClient, path: str
    ) -> None:
        response = await page.options(path, headers=preflight("POST"))

        assert "access-control-allow-origin" not in response.headers
        assert response.status_code != 204

    async def test_a_path_that_only_starts_like_a_closed_one_is_not_closed(
        self, page: httpx.AsyncClient
    ) -> None:
        response = await page.options("/authors", headers=preflight("GET"))

        assert response.status_code == 204


class TestWhichRoutesAreBearerRoutes:
    def test_only_a_route_of_the_service_can_be_one(self, igni: IgniService) -> None:
        routes = BearerRoutes(igni)

        assert routes.is_bearer(None) is False
        assert routes.is_bearer(Mount("/static", app=FastAPI())) is False
        assert routes.is_bearer("/v1/notes") is False

    def test_a_route_is_judged_once(self, igni: IgniService, cors_app: FastAPI) -> None:
        routes = BearerRoutes(igni)
        judged: list[object] = []
        original = routes._judge

        def counting(dependant: Any) -> bool:
            judged.append(dependant)
            return original(dependant)

        routes._judge = counting  # type: ignore[method-assign]
        [route] = [r for r in cors_app.routes if getattr(r, "path", "") == "/v1/public"]

        assert [routes.is_bearer(route) for _ in range(3)] == [True, True, True]
        assert len(judged) == 1

    def test_a_route_with_no_dependencies_is_not_one(self, igni: IgniService) -> None:
        app = FastAPI()

        @app.get("/open")
        async def open_() -> dict[str, str]:
            return {}

        [route] = [r for r in app.routes if getattr(r, "path", "") == "/open"]

        assert BearerRoutes(igni).is_bearer(route) is False


async def _never_received() -> Message:
    raise AssertionError("the middleware read the request")


async def _never_sent(message: Message) -> None:
    raise AssertionError("the middleware answered")
