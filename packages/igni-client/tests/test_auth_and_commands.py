"""Signing in as a person, an app or a space, and running commands in a VM."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import jwt
import pytest

from igni_client import (
    ApiKey,
    App,
    AuthError,
    IgniClient,
    NotAllowed,
    NotSupported,
    Person,
)
from igni_client.events import Unknown, parse_event
from igni_client.testing import CommandResult, FakeIgni

ISSUER = "https://igni.example.test"


class IgniServer:
    """igni server's discovery, token endpoint and spaces, as an `httpx.MockTransport`."""

    def __init__(self, app: dict[str, Any] | None = None) -> None:
        self.jwks: dict[str, Any] | None = None
        self.token_requests: list[dict[str, str]] = []
        self.spaces: dict[str, dict[str, Any]] = {}
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISSUER})
        if path == "/v1/oauth/token":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.token_requests.append(form)
            if form["grant_type"] == "client_credentials":
                header = jwt.get_unverified_header(form["client_assertion"])
                key = jwt.PyJWK(self.jwks["keys"][0]) if self.jwks else None
                if key is None or header.get("kid") != key.key_id:
                    return httpx.Response(401, json={"error": "invalid_client"})
                # Signature, key and audience are checked; time is the test's own clock.
                claims = jwt.decode(
                    form["client_assertion"],
                    key.key,
                    algorithms=["RS256"],
                    audience=ISSUER,
                    options={"verify_exp": False, "verify_iat": False},
                )
                return httpx.Response(
                    200, json={"access_token": f"app:{claims['sub']}", "expires_in": 600}
                )
            if form["grant_type"].endswith("token-exchange"):
                return httpx.Response(
                    200, json={"access_token": f"space:{form['space']}", "expires_in": 600}
                )
        if path.startswith("/v1/apps/") and "/spaces" in path:
            if request.headers.get("Authorization") != "Bearer app:app-bot":
                return httpx.Response(401)
            external_id = path.rsplit("/", 1)[-1]
            if request.method == "PUT":
                record = self.spaces.setdefault(
                    external_id,
                    {
                        "space_id": f"sp-{len(self.spaces) + 1}",
                        "app_id": "app-bot",
                        "external_id": external_id,
                    },
                )
                return httpx.Response(201, json=record)
            if request.method == "DELETE":
                self.spaces.pop(external_id, None)
                return httpx.Response(204)
        return httpx.Response(404)


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    return App.generate_key(tmp_path / "app-key.pem")


def _app(key_file: Path, server: IgniServer, clock: Any = None) -> App:
    http = httpx.AsyncClient(transport=httpx.MockTransport(server))
    kwargs: dict[str, Any] = {"server": "http://igni.test", "key_file": key_file, "http": http}
    if clock is not None:
        kwargs["clock"] = clock
    return App("app-bot", **kwargs)


async def test_an_app_signs_in_with_its_registered_key_and_keeps_the_token(key_file: Path) -> None:
    server = IgniServer()
    app = _app(key_file, server)
    server.jwks = app.public_jwks()

    first, second = await app.token(), await app.token()

    assert first == second == "app:app-bot"
    assert len(server.token_requests) == 1
    assert key_file.stat().st_mode & 0o777 == 0o600


async def test_an_app_renews_its_token_before_it_runs_out(key_file: Path) -> None:
    now = [1_000.0]
    server = IgniServer()
    app = _app(key_file, server, clock=lambda: now[0])
    server.jwks = app.public_jwks()

    await app.token()
    now[0] += 600 - App.RENEW_BEFORE + 1
    await app.token()

    assert len(server.token_requests) == 2


async def test_an_unregistered_key_is_an_auth_error(key_file: Path) -> None:
    app = _app(key_file, IgniServer())
    with pytest.raises(AuthError, match="refused"):
        await app.token()


async def test_a_space_is_declared_and_signed_in_by_exchanging_the_apps_token(
    key_file: Path,
) -> None:
    server = IgniServer()
    app = _app(key_file, server)
    server.jwks = app.public_jwks()

    space = await app.spaces.declare("customer-42")
    again = await app.spaces.declare("customer-42")
    token = await space.token()
    await app.spaces.delete("customer-42")

    assert space.space_id == again.space_id == "sp-1"
    assert space.external_id == "customer-42"
    assert token == "space:sp-1"
    exchange = server.token_requests[-1]
    assert exchange["subject_token"] == "app:app-bot" and exchange["space"] == "sp-1"
    assert "customer-42" not in server.spaces


async def test_a_space_id_with_a_slash_is_refused_before_asking(key_file: Path) -> None:
    app = _app(key_file, IgniServer())
    with pytest.raises(ValueError, match="without '/'"):
        await app.spaces.declare("a/b")


class KeyExchange:
    """igni server's api-key grant, as an `httpx.MockTransport`."""

    def __init__(self, *, refuse: str = "") -> None:
        self.forms: list[dict[str, str]] = []
        self.refuse = refuse

    def __call__(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.forms.append(form)
        if self.refuse:
            return httpx.Response(
                400, json={"error": "invalid_grant", "error_description": self.refuse}
            )
        return httpx.Response(
            200, json={"access_token": f"session-{len(self.forms)}", "expires_in": 900}
        )


def _key(exchange: KeyExchange, clock: Any = None) -> ApiKey:
    http = httpx.AsyncClient(transport=httpx.MockTransport(exchange))
    return ApiKey(
        "igpak1.org.k1.secret", server="http://igni.test", http=http, clock=clock or (lambda: 0.0)
    )


async def test_an_api_key_buys_a_session_and_keeps_it_until_near_its_end() -> None:
    now = [1_000.0]
    exchange = KeyExchange()
    key = _key(exchange, clock=lambda: now[0])

    first, again = await key.token(), await key.token()
    now[0] += 900 - ApiKey.RENEW_BEFORE + 1
    renewed = await key.token()

    assert first == again == "session-1" and renewed == "session-2"
    assert exchange.forms[0] == {
        "grant_type": "urn:igni:params:oauth:grant-type:api-key",
        "api_key": "igpak1.org.k1.secret",
    }


async def test_a_revoked_key_is_an_auth_error_with_igni_s_reason() -> None:
    key = _key(KeyExchange(refuse="this API key has been revoked"))

    with pytest.raises(AuthError, match="this API key has been revoked"):
        await key.token()


def test_an_api_key_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IGNI_API_KEY", "igpak1.org.k1.secret")
    monkeypatch.setenv("IGNI_SERVER_URL", "http://igni.test/")

    key = Person.from_api_key()

    assert key.server == "http://igni.test"
    assert "secret" not in repr(key)


def test_a_missing_or_malformed_key_says_what_to_do(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IGNI_API_KEY", raising=False)
    with pytest.raises(AuthError, match="IGNI_API_KEY"):
        Person.from_api_key(server="http://igni.test")
    with pytest.raises(AuthError, match="igpak1"):
        Person.from_api_key("eyJ-a-session-not-a-key", server="http://igni.test")


def test_a_person_comes_from_the_cli_credentials(tmp_path: Path) -> None:
    stored = tmp_path / "credentials.json"
    later = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    stored.write_text(json.dumps({"access_token": "t-ada", "expires_at": later}))

    assert Person.from_cli(stored)._token == "t-ada"


def test_an_expired_or_missing_session_says_to_sign_in(tmp_path: Path) -> None:
    stored = tmp_path / "credentials.json"
    stored.write_text(json.dumps({"access_token": "t", "expires_at": "2020-01-01T00:00:00+00:00"}))
    with pytest.raises(AuthError, match="igni login"):
        Person.from_cli(stored)
    with pytest.raises(AuthError, match="igni login"):
        Person.from_cli(tmp_path / "nothing.json")


async def test_a_command_streams_its_output_and_ends_with_its_exit_code() -> None:
    async with FakeIgni(gateway=True, tokens={"t-ada": "person:u-ada"}) as fake:
        fake.commands["make test"] = CommandResult(stdout="ok\n", stderr="warn\n", exit_code=2)
        async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
            run = await igni.commands.run("make test", timeout_s=30)
            finished = await run.wait()
            me = await igni.me()

    assert run.stdout == "ok\n" and run.stderr == "warn\n"
    assert finished.exit_code == 2 and not finished.ok
    assert run.woken["how"] == "paused" and run.record["command"] == "make test"
    assert fake.commands_run[0]["producer"] == {"kind": "person", "id": "u-ada"}
    assert (me.kind, me.id, me.org) == ("person", "u-ada", "org-acme")


async def test_a_command_in_somebody_elses_vm_is_refused() -> None:
    async with (
        FakeIgni(gateway=True, tokens={"t-ada": "person:u-ada"}) as fake,
        IgniClient(fake.fleet(Person("t-ada"))) as igni,
    ):
        run = await igni.commands.run("id", producer="person:u-bob")
        with pytest.raises(NotAllowed, match="not your VM"):
            await run.wait()


async def test_a_local_igni_has_no_commands() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        with pytest.raises(NotSupported, match="needs Fleet's gateway"):
            await igni.commands.run("ls")


def test_a_message_this_version_does_not_know_keeps_everything() -> None:
    event = parse_event({"type": "hologram", "id": "x", "colour": "teal"})

    assert isinstance(event, Unknown)
    assert event.type == "hologram" and event.model_extra == {"colour": "teal"}


def test_a_newer_field_on_a_known_message_is_kept() -> None:
    event = parse_event({"type": "content_delta", "text": "hi", "language": "en"})

    assert event.type == "content_delta" and event.model_extra == {"language": "en"}
