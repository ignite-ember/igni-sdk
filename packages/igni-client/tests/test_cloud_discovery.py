"""Finding a person's cloud igni from igni server: `discover()`, `set_events_owner()`, `Fleet.from_server`.

igni server's `/v1/me/cloud` is igni-sdk's own contract,
`contracts/cloud-discovery.schema.json`. igni-client's model is held to it
field for field, every answer the fake igni server gives is valid under it,
and the client reads an answer leniently in the safe direction the
contract names.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args

import httpx
import pytest
from jsonschema import Draft202012Validator

from igni_client import (
    AuthError,
    CloudGroup,
    CloudIgni,
    Fleet,
    GroupIsLocalOnly,
    IgniClient,
    NotAllowed,
    NotSupported,
    Person,
    Unavailable,
    discover,
    set_events_owner,
)
from igni_client.cloud import (
    INSECURE_GATEWAY_ENV,
    REASONS,
    CloudState,
    EventsOwner,
    EventsOwnerRequest,
    Mode,
    checked_gateway,
    insecure_gateway_allowed,
)
from igni_client.testing import FakeGateway, FakeIgni, FakeServer, Steps

SCHEMA_FILE = Path(__file__).resolve().parents[3] / "contracts" / "cloud-discovery.schema.json"
SCHEMA: dict[str, Any] = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
DEFS: dict[str, Any] = SCHEMA["$defs"]
TOKENS = {"t-ada": "person:u-ada", "t-bot": "app:bot", "t-space": "space:sp-1"}
SERVER = "http://igni.test"


def validator(name: str | None = None) -> Draft202012Validator:
    if name is None:
        return Draft202012Validator(SCHEMA)
    return Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": DEFS})


def server_http(server: FakeServer) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=server.transport())


def fake_server(**settings: Any) -> FakeServer:
    server = FakeServer(TOKENS, gateway_url=lambda: "https://fleet.acme.example")
    for name, value in settings.items():
        setattr(server, name, value)
    return server


# ── The model is the contract's ──


def test_the_model_s_fields_are_the_contract_s_required_fields() -> None:
    assert set(CloudIgni.model_fields) == set(DEFS["CloudDiscovery"]["required"])
    assert set(CloudGroup.model_fields) == set(DEFS["Group"]["required"])
    assert set(EventsOwnerRequest.model_fields) == set(DEFS["EventsOwnerRequest"]["required"])


def test_the_model_s_words_are_the_contract_s() -> None:
    assert list(get_args(CloudState)) == DEFS["Cloud"]["enum"]
    assert list(get_args(Mode)) == DEFS["Mode"]["enum"]
    assert list(get_args(EventsOwner)) == DEFS["EventsOwner"]["enum"]
    [reasons] = [branch["enum"] for branch in DEFS["Reason"]["oneOf"] if "enum" in branch]
    assert list(REASONS) == reasons


@pytest.mark.parametrize("example", DEFS["CloudDiscovery"]["examples"])
def test_every_example_reads_and_dumps_back_as_it_came(example: dict[str, Any]) -> None:
    read = CloudIgni.model_validate(example)
    assert read.model_dump(mode="json") == example
    assert validator().is_valid(read.model_dump(mode="json"))


@pytest.mark.parametrize("owner", ["local", "cloud"])
def test_the_events_owner_body_is_valid(owner: EventsOwner) -> None:
    assert validator("EventsOwnerRequest").is_valid(EventsOwnerRequest(owner=owner).model_dump())


# ── Read leniently, in the safe direction ──


def test_a_newer_server_s_words_read_the_safe_way() -> None:
    read = CloudIgni.model_validate(
        {
            "cloud": "partly",
            "reason": "maintenance",
            "gateway_url": "https://gw",
            "mode": "hybrid",
            "events_owner": "both",
            "group": {"id": "g", "name": "G", "colour": "red"},
            "producer": "person:u",
            "vm_profile": "standard",
        }
    )
    assert (read.cloud, read.mode, read.events_owner) == ("unavailable", "local", "local")
    assert read.reason == "maintenance"
    assert read.model_extra == {"vm_profile": "standard"}
    assert read.group is not None and read.group.model_extra == {"colour": "red"}
    assert not read.available


def test_missing_fields_read_as_no_cloud_igni() -> None:
    read = CloudIgni.model_validate({})
    assert (read.cloud, read.mode, read.events_owner, read.group) == (
        "unavailable",
        "local",
        "local",
        None,
    )
    assert not read.available


@pytest.mark.parametrize(
    ("changes", "available"),
    [
        ({}, True),
        ({"mode": "cloud", "events_owner": "cloud"}, True),
        ({"cloud": "unavailable", "reason": "inactive"}, False),
        ({"mode": "local"}, False),
        ({"gateway_url": None}, False),
        ({"gateway_url": ""}, False),
    ],
)
def test_available_needs_the_word_a_gateway_and_a_group_that_allows_it(
    changes: dict[str, Any], available: bool
) -> None:
    body = {**DEFS["CloudDiscovery"]["examples"][0], **changes}
    assert CloudIgni.model_validate(body).available is available


@pytest.mark.parametrize(
    ("mode", "allows"), [("local", True), ("local_and_cloud", True), ("cloud", False)]
)
def test_only_a_cloud_group_keeps_igni_off_the_person_s_computer(mode: Mode, allows: bool) -> None:
    assert CloudIgni(mode=mode).allows_local is allows


def test_an_available_cloud_igni_refuses_nothing() -> None:
    assert CloudIgni.model_validate(DEFS["CloudDiscovery"]["examples"][0]).refusal() is None


@pytest.mark.parametrize(
    ("cloud", "kind", "words"),
    [
        (
            CloudIgni(cloud="unavailable", reason="group_local_only", mode="local"),
            GroupIsLocalOnly,
            "group_local_only",
        ),
        (
            CloudIgni(cloud="available", gateway_url="https://gw", mode="local"),
            GroupIsLocalOnly,
            "",
        ),
        (
            CloudIgni(cloud="unavailable", reason="group_local_only", mode="local_and_cloud"),
            GroupIsLocalOnly,
            "",
        ),
        (
            CloudIgni(cloud="unavailable", reason="fleet_not_configured", mode="local_and_cloud"),
            NotSupported,
            "no Fleet",
        ),
        (CloudIgni(cloud="available", mode="local_and_cloud"), NotSupported, "no Fleet"),
        (
            CloudIgni(
                cloud="unavailable", reason="inactive", gateway_url="https://gw", mode="cloud"
            ),
            NotAllowed,
            "(inactive)",
        ),
        (
            CloudIgni(
                cloud="unavailable", reason="not_licensed", gateway_url="https://gw", mode="cloud"
            ),
            NotAllowed,
            "(not_licensed)",
        ),
        (
            CloudIgni(cloud="unavailable", gateway_url="https://gw", mode="cloud"),
            NotAllowed,
            "(unavailable)",
        ),
    ],
)
def test_each_reason_is_the_error_connecting_would_raise(
    cloud: CloudIgni, kind: type[Exception], words: str
) -> None:
    refusal = cloud.refusal()
    assert type(refusal) is kind
    assert words in str(refusal)


def test_an_inactive_person_is_not_told_their_group_is_local_only() -> None:
    refusal = CloudIgni(
        cloud="unavailable", reason="inactive", gateway_url="https://gw", mode="local_and_cloud"
    ).refusal()
    assert isinstance(refusal, NotAllowed) and not isinstance(refusal, GroupIsLocalOnly)


# ── The fake igni server answers as the contract says ──


@pytest.mark.parametrize("mode", get_args(Mode))
@pytest.mark.parametrize("fleet", [True, False])
@pytest.mark.parametrize("standing", ["active", "inactive", "not_licensed"])
@pytest.mark.parametrize("chosen", [None, "local", "cloud"])
def test_every_answer_the_fake_gives_is_valid(
    mode: Mode, fleet: bool, standing: str, chosen: EventsOwner | None
) -> None:
    server = fake_server(mode=mode, fleet_configured=fleet)
    if standing != "active":
        getattr(server, standing).add("person:u-ada")
    if chosen is not None:
        server.events_owners["person:u-ada"] = chosen
    body = server.answer("person:u-ada").model_dump(mode="json")
    errors = [e.message for e in validator().iter_errors(body)]
    assert errors == []


def test_a_person_in_no_group_is_valid_too() -> None:
    server = fake_server(group=None)
    assert validator().is_valid(server.answer("person:u-ada").model_dump(mode="json"))


@pytest.mark.parametrize(
    ("token", "status"), [("t-bot", 403), ("t-space", 403), ("nobody", 401), (None, 401)]
)
def test_the_fake_s_refusals_are_the_contract_s(token: str | None, status: int) -> None:
    server = fake_server()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = server.handle(httpx.Request("GET", f"{SERVER}/v1/me/cloud", headers=headers))
    assert response.status_code == status
    assert validator("Refusal").is_valid(response.json())


def test_the_fake_s_mode_forbids_is_the_contract_s() -> None:
    server = fake_server(mode="local")
    response = server.handle(
        httpx.Request(
            "PUT",
            f"{SERVER}/v1/me/cloud/events-owner",
            headers={"Authorization": "Bearer t-ada"},
            json={"owner": "cloud"},
        )
    )
    assert response.status_code == 409
    assert validator("ModeForbids").is_valid(response.json())


def test_the_fake_answers_cache_control_and_its_discovery_names_the_gateway() -> None:
    server = fake_server()
    cloud = server.handle(
        httpx.Request("GET", f"{SERVER}/v1/me/cloud", headers={"Authorization": "Bearer t-ada"})
    )
    assert cloud.headers["Cache-Control"] == "private, max-age=60"
    found = server.handle(httpx.Request("GET", f"{SERVER}/.well-known/openid-configuration"))
    assert found.json() == {"issuer": SERVER, "igni_gateway": "https://fleet.acme.example"}
    server.fleet_configured = False
    found = server.handle(httpx.Request("GET", f"{SERVER}/.well-known/openid-configuration"))
    assert found.json() == {"issuer": SERVER}


@pytest.mark.parametrize(
    ("method", "path", "body", "status"),
    [
        ("POST", "/v1/me/cloud", None, 405),
        ("GET", "/v1/me/cloud/events-owner", None, 405),
        ("PUT", "/v1/me/cloud/events-owner", {"owner": "both"}, 422),
        ("GET", "/v1/elsewhere", None, 404),
    ],
)
def test_the_fake_refuses_what_igni_server_does_not_serve(
    method: str, path: str, body: Any, status: int
) -> None:
    request = httpx.Request(
        method, f"{SERVER}{path}", headers={"Authorization": "Bearer t-ada"}, json=body
    )
    assert fake_server().handle(request).status_code == status


# ── discover() ──


async def test_discover_asks_with_the_person_s_session_and_reads_the_answer() -> None:
    server = fake_server()
    cloud = await discover(SERVER, Person("t-ada"), http=server_http(server))
    assert cloud == CloudIgni(
        cloud="available",
        reason=None,
        gateway_url="https://fleet.acme.example",
        mode="local_and_cloud",
        events_owner="local",
        group=CloudGroup(id="g-engineering", name="Engineering"),
        producer="person:u-ada",
    )
    [asked] = server.calls
    assert (asked.method, asked.url.path) == ("GET", "/v1/me/cloud")
    assert asked.headers["Authorization"] == "Bearer t-ada"


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        ({"mode": "local"}, ("unavailable", "group_local_only", "local", "local")),
        ({"mode": "cloud"}, ("available", None, "cloud", "cloud")),
        ({"mode": "local_and_cloud"}, ("available", None, "local_and_cloud", "local")),
        (
            {"fleet_configured": False},
            ("unavailable", "fleet_not_configured", "local_and_cloud", "local"),
        ),
        ({"inactive": {"person:u-ada"}}, ("unavailable", "inactive", "local_and_cloud", "local")),
        (
            {"not_licensed": {"person:u-ada"}},
            ("unavailable", "not_licensed", "local_and_cloud", "local"),
        ),
    ],
)
async def test_discover_reads_each_answer(
    settings: dict[str, Any], expected: tuple[Any, ...]
) -> None:
    cloud = await discover(SERVER, Person("t-ada"), http=server_http(fake_server(**settings)))
    assert (cloud.cloud, cloud.reason, cloud.mode, cloud.events_owner) == expected


@pytest.mark.parametrize("token", ["t-bot", "t-space"])
async def test_discover_is_refused_for_an_app_or_a_space(token: str) -> None:
    with pytest.raises(NotAllowed, match="only a person's session") as raised:
        await discover(SERVER, Person(token), http=server_http(fake_server()))
    assert not isinstance(raised.value, GroupIsLocalOnly)


async def test_discover_with_a_refused_session_is_an_auth_error() -> None:
    with pytest.raises(
        AuthError, match="refused the session for cloud discovery: Not authenticated"
    ):
        await discover(SERVER, Person("t-gone"), http=server_http(fake_server()))


async def test_an_older_server_is_read_from_its_igni_gateway() -> None:
    server = fake_server(serves_cloud=False)
    cloud = await discover(SERVER, Person("t-ada"), http=server_http(server))
    assert (cloud.cloud, cloud.reason, cloud.gateway_url, cloud.mode, cloud.events_owner) == (
        "available",
        None,
        "https://fleet.acme.example",
        "local_and_cloud",
        "local",
    )
    assert [c.url.path for c in server.calls] == [
        "/v1/me/cloud",
        "/.well-known/openid-configuration",
    ]


async def test_an_older_server_without_fleet_has_no_cloud_igni() -> None:
    server = fake_server(serves_cloud=False, fleet_configured=False)
    cloud = await discover(SERVER, Person("t-ada"), http=server_http(server))
    assert (cloud.cloud, cloud.reason, cloud.gateway_url) == (
        "unavailable",
        "fleet_not_configured",
        None,
    )
    assert isinstance(cloud.refusal(), NotSupported)


@pytest.mark.parametrize(
    "document",
    [{"issuer": SERVER, "igni_gateway": 5}, {"issuer": SERVER, "igni_gateway": ""}, "not json"],
)
async def test_an_older_server_s_gateway_that_is_not_an_address_is_none(document: Any) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/me/cloud":
            return httpx.Response(404)
        if isinstance(document, str):
            return httpx.Response(200, text=document)
        return httpx.Response(200, json=document)

    http = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    cloud = await discover(SERVER, Person("t-ada"), http=http)
    assert (cloud.cloud, cloud.reason) == ("unavailable", "fleet_not_configured")


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(200, text="<html>"), "with something else"),
        (
            httpx.Response(200, json={"cloud": "available", "group": "Engineering"}),
            "with something else",
        ),
        (httpx.Response(500, text="boom"), "with 500"),
        (httpx.Response(409, json={"error": "other"}), "with 409"),
    ],
)
async def test_an_answer_that_is_not_the_contract_s_is_unavailable(
    response: httpx.Response, message: str
) -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response))
    with pytest.raises(Unavailable, match=message):
        await discover(SERVER, Person("t-ada"), http=http)


async def test_an_unreachable_server_is_unavailable() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(down))
    with pytest.raises(Unavailable, match="could not reach igni server for cloud discovery"):
        await discover(SERVER, Person("t-ada"), http=http)


async def test_discover_closes_only_a_client_it_made() -> None:
    http = server_http(fake_server())
    await discover(SERVER, Person("t-ada"), http=http)
    assert not http.is_closed


# ── set_events_owner() ──


@pytest.mark.parametrize(
    ("mode", "owner"),
    [
        ("local_and_cloud", "cloud"),
        ("local_and_cloud", "local"),
        ("cloud", "cloud"),
        ("local", "local"),
    ],
)
async def test_the_owner_a_mode_allows_is_set_and_answered(mode: Mode, owner: EventsOwner) -> None:
    server = fake_server(mode=mode)
    cloud = await set_events_owner(SERVER, Person("t-ada"), owner, http=server_http(server))
    assert cloud.events_owner == owner
    [asked] = server.calls
    assert (asked.method, asked.url.path) == ("PUT", "/v1/me/cloud/events-owner")
    assert json.loads(asked.content) == {"owner": owner}
    assert asked.headers["Authorization"] == "Bearer t-ada"


async def test_the_choice_holds_for_the_next_discovery() -> None:
    server = fake_server()
    await set_events_owner(SERVER, Person("t-ada"), "cloud", http=server_http(server))
    assert (
        await discover(SERVER, Person("t-ada"), http=server_http(server))
    ).events_owner == "cloud"


@pytest.mark.parametrize(("mode", "owner"), [("local", "cloud"), ("cloud", "local")])
async def test_an_owner_the_mode_forbids_is_not_allowed(mode: Mode, owner: EventsOwner) -> None:
    server = fake_server(mode=mode)
    with pytest.raises(NotAllowed, match="mode_forbids"):
        await set_events_owner(SERVER, Person("t-ada"), owner, http=server_http(server))
    assert server.events_owners == {}


async def test_an_owner_that_is_not_one_is_refused_before_asking() -> None:
    server = fake_server()
    with pytest.raises(ValueError, match="'cloud' or 'local'"):
        await set_events_owner(SERVER, Person("t-ada"), "both", http=server_http(server))  # type: ignore[arg-type]
    assert server.calls == []


async def test_an_app_cannot_choose_a_person_s_events_owner() -> None:
    with pytest.raises(NotAllowed, match="only a person's session"):
        await set_events_owner(SERVER, Person("t-bot"), "cloud", http=server_http(fake_server()))


# ── Fleet.from_server ──


async def test_from_server_connects_to_the_gateway_igni_server_names() -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        fake.runs.script = lambda text: Steps.answer(f"cloud says {text}")
        fleet = await Fleet.from_server(
            fake.server_url, auth=Person("t-ada"), http=fake.server_http(), allow_http=True
        )
        assert fleet.base == f"http://127.0.0.1:{fake.socket.port}"
        assert fleet.discovered is not None and fleet.discovered.producer == "person:u-ada"
        async with IgniClient(fleet) as igni:
            session = await igni.sessions.create()
            assert str(await session.ask("hi")) == "cloud says hi"
            assert (await igni.me()).producer == "person:u-ada"


async def test_a_fleet_made_by_hand_was_not_discovered() -> None:
    assert Fleet("https://gw", auth=Person("t-ada")).discovered is None


async def test_from_server_refuses_a_plain_http_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(INSECURE_GATEWAY_ENV, raising=False)
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        with pytest.raises(NotAllowed, match="not https") as raised:
            await Fleet.from_server(fake.server_url, auth=Person("t-ada"), http=fake.server_http())
        assert INSECURE_GATEWAY_ENV in str(raised.value)
        assert fake.socket.connections == 0


async def test_the_development_switch_takes_a_plain_http_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(INSECURE_GATEWAY_ENV, "1")
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        fleet = await Fleet.from_server(
            fake.server_url, auth=Person("t-ada"), http=fake.server_http()
        )
        assert fleet.base.startswith("http://127.0.0.1:")
        with pytest.raises(NotAllowed, match="not https"):
            await Fleet.from_server(
                fake.server_url, auth=Person("t-ada"), http=fake.server_http(), allow_http=False
            )


@pytest.mark.parametrize(
    ("value", "allowed"), [("1", True), ("0", False), ("true", False), ("", False)]
)
def test_only_one_turns_the_development_switch_on(
    monkeypatch: pytest.MonkeyPatch, value: str, allowed: bool
) -> None:
    monkeypatch.setenv(INSECURE_GATEWAY_ENV, value)
    assert insecure_gateway_allowed() is allowed


@pytest.mark.parametrize(
    ("url", "allow_http", "ok"),
    [
        ("https://gw.acme", False, True),
        ("http://gw.acme", True, True),
        ("http://gw.acme", False, False),
        ("ws://gw.acme", True, False),
        ("ftp://gw.acme", True, False),
    ],
)
def test_the_gateway_must_speak_tls(url: str, allow_http: bool, ok: bool) -> None:
    cloud = CloudIgni(cloud="available", gateway_url=url, mode="local_and_cloud")
    if ok:
        assert checked_gateway(cloud, allow_http=allow_http) == url
    else:
        with pytest.raises(NotAllowed, match="not https"):
            checked_gateway(cloud, allow_http=allow_http)


@pytest.mark.parametrize(
    ("settings", "kind"),
    [
        ({"mode": "local"}, GroupIsLocalOnly),
        ({"fleet_configured": False}, NotSupported),
        ({"inactive": {"person:u-ada"}}, NotAllowed),
        ({"not_licensed": {"person:u-ada"}}, NotAllowed),
    ],
)
async def test_from_server_raises_what_connecting_would(
    settings: dict[str, Any], kind: type[Exception]
) -> None:
    async with FakeIgni(gateway=FakeGateway(TOKENS)) as fake:
        assert fake.server is not None
        for name, value in settings.items():
            setattr(fake.server, name, value)
        with pytest.raises(kind) as raised:
            await Fleet.from_server(
                fake.server_url, auth=Person("t-ada"), http=fake.server_http(), allow_http=True
            )
        assert type(raised.value) is kind
        assert fake.socket.connections == 0


async def test_from_server_makes_and_closes_its_own_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = fake_server()
    made: list[httpx.AsyncClient] = []
    real = httpx.AsyncClient

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        made.append(real(transport=server.transport()))
        return made[-1]

    monkeypatch.setattr(httpx, "AsyncClient", client)
    fleet = await Fleet.from_server(SERVER, auth=Person("t-ada"))
    assert fleet.base == "https://fleet.acme.example"
    assert made[0].is_closed  # igni server's, closed once discovery is done
    assert not made[1].is_closed  # the gateway's, the Fleet's own
    await fleet.aclose()
    assert made[1].is_closed


# ── The fake's own wiring ──


async def test_the_fake_has_no_server_without_a_gateway() -> None:
    fake = FakeIgni()
    assert fake.server is None
    with pytest.raises(RuntimeError, match="plays igni server's discovery"):
        _ = fake.server_url
    with pytest.raises(RuntimeError, match="plays igni server's discovery"):
        fake.server_http()
    with pytest.raises(RuntimeError, match="plays igni server's discovery"):
        await fake.set_mode("local")
