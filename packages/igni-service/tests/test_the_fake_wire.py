"""The fake's wire types, one at a time: addresses, what was seen, the two error bodies, the traffic.

The router uses these everywhere; these read them directly, so an edge
(a trailing slash, a repeated key, a body that is not text) is pinned
where it is decided and not only where a route happens to meet it.
"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from igni_service.testing import FakeIgni
from igni_service.testing_wire import (
    BASE,
    ISSUER,
    SERVICE_URL,
    DetailError,
    IgniAddresses,
    OAuthError,
    RecordedTraffic,
    SeenRequest,
    TokenForm,
)
from igni_service.token_endpoint import ASSERTION_TYPE
from igni_service.urls import IgniPaths


def seen(
    method: str = "GET",
    url: str = "http://igni.test/v1/x",
    *,
    headers: dict[str, str] | None = None,
    content: bytes = b"",
) -> SeenRequest:
    return SeenRequest.of(httpx.Request(method, url, headers=headers, content=content))


class TestAddresses:
    def test_the_fake_is_reached_at_one_address_and_names_another_as_its_issuer(self) -> None:
        addresses = IgniAddresses()

        assert (addresses.base_url, addresses.issuer, addresses.service_url) == (
            "http://igni.test",
            "https://igni.example.test",
            "http://service.test",
        )
        assert (
            addresses.base_url,
            addresses.issuer,
            addresses.service_url,
        ) == (BASE, ISSUER, SERVICE_URL)
        assert FakeIgni.BASE == BASE and FakeIgni.ISSUER == ISSUER

    def test_a_trailing_slash_is_dropped_from_the_base_and_the_issuer(self) -> None:
        addresses = IgniAddresses(base_url="http://a.test//", issuer="https://b.test/")

        assert addresses.base_url == "http://a.test"
        assert addresses.issuer == "https://b.test"
        assert addresses.authorization_endpoint == "https://b.test/authorize"

    def test_the_service_url_is_written_as_igni_writes_it(self) -> None:
        assert IgniAddresses(service_url="HTTP://Svc.Test:80/").service_url == (
            "http://svc.test:80"
        )
        with pytest.raises(ValidationError, match="not an absolute http"):
            IgniAddresses(service_url="svc.test")

    def test_addresses_are_frozen(self) -> None:
        with pytest.raises(ValidationError):
            IgniAddresses().base_url = "http://other.test"

    @pytest.mark.parametrize(
        ("url", "reached"),
        [
            ("http://igni.test/v1/anything?q=1", True),
            ("http://igni.test", True),
            ("https://igni.test/v1/x", False),
            ("http://igni.test:8080/v1/x", False),
            ("http://other.test/v1/x", False),
            ("http://igni.example.test/v1/x", False),
        ],
    )
    def test_a_url_reaches_the_fake_by_scheme_and_host_and_port_not_by_path(
        self, url: str, reached: bool
    ) -> None:
        assert IgniAddresses().reaches(url) is reached

    def test_an_assertion_may_be_addressed_to_the_issuer_or_either_endpoint_under_it(self) -> None:
        assert IgniAddresses().assertion_audiences() == [
            "https://igni.example.test",
            f"https://igni.example.test{IgniPaths.TOKEN}",
            f"https://igni.example.test{IgniPaths.REVOKE}",
        ]

    def test_discovery_puts_every_endpoint_under_the_issuer_not_the_address_it_is_reached_at(
        self,
    ) -> None:
        document = IgniAddresses(issuer="https://pub.test/").discovery()

        assert document.model_dump() == {
            "issuer": "https://pub.test",
            "authorization_endpoint": "https://pub.test/authorize",
            "jwks_uri": f"https://pub.test{IgniPaths.JWKS}",
            "token_endpoint": f"https://pub.test{IgniPaths.TOKEN}",
            "revocation_endpoint": f"https://pub.test{IgniPaths.REVOKE}",
        }


class TestErrorBodies:
    def test_a_detail_error_answers_with_its_status_and_only_the_detail(self) -> None:
        response = DetailError(detail="why", status=409).to_response()

        assert response.status_code == 409
        assert response.json() == {"detail": "why"}

    def test_a_detail_error_is_a_400_unless_told(self) -> None:
        assert DetailError(detail="x").to_response().status_code == 400

    def test_not_found_and_not_authenticated_are_igni_s_words(self) -> None:
        missing = DetailError.not_found().to_response()
        unknown = DetailError.not_authenticated().to_response()

        assert (missing.status_code, missing.json()) == (404, {"detail": "Not Found"})
        assert (unknown.status_code, unknown.json()) == (401, {"detail": "Not authenticated"})

    def test_an_oauth_error_leaves_out_what_it_does_not_say_and_its_status(self) -> None:
        response = OAuthError(error="invalid_grant").to_response()

        assert response.status_code == 400
        assert response.json() == {"error": "invalid_grant"}

    def test_an_oauth_error_carries_its_description_and_the_client_s_state(self) -> None:
        response = OAuthError(
            error="invalid_client",
            error_description="not approved",
            client_state="pending",
            status=401,
        ).to_response()

        assert response.status_code == 401
        assert response.json() == {
            "error": "invalid_client",
            "error_description": "not approved",
            "client_state": "pending",
        }


class TestTokenForm:
    def test_a_form_that_says_nothing_is_all_empty_strings(self) -> None:
        form = TokenForm()

        assert all(value == "" for value in form.model_dump().values())
        assert not form.is_jwt_bearer

    def test_unknown_fields_are_ignored(self) -> None:
        form = TokenForm.model_validate({"grant_type": "refresh_token", "surprise": "x"})

        assert form.grant_type == "refresh_token"
        assert not hasattr(form, "surprise")

    def test_only_the_jwt_bearer_assertion_type_is_a_jwt_bearer(self) -> None:
        assert TokenForm(client_assertion_type=ASSERTION_TYPE).is_jwt_bearer
        assert not TokenForm(client_assertion_type="urn:other").is_jwt_bearer
        assert not TokenForm(client_assertion_type=ASSERTION_TYPE.upper()).is_jwt_bearer


class TestWhatWasSeen:
    def test_a_request_is_kept_whole_with_its_path_cut_from_its_query(self) -> None:
        request = seen(
            "POST",
            "http://igni.test/v1/things?a=1&a=2&b=&c=x%20y",
            headers={"X-Mixed-Case": "Yes", "Authorization": "Bearer t"},
            content=b"payload",
        )

        assert request.method == "POST"
        assert request.path == "/v1/things"
        assert request.body == b"payload"
        assert request.headers["x-mixed-case"] == "Yes"
        assert "X-Mixed-Case" not in request.headers
        # A parameter with no value is dropped by the parser, as igni's is.
        assert request.query == {"a": ["1", "2"], "c": ["x y"]}

    def test_an_empty_body_is_empty_bytes(self) -> None:
        assert seen().body == b""

    def test_json_is_read_from_the_body_and_invalid_json_is_not_hidden(self) -> None:
        assert seen("POST", content=b'{"a": [1, 2]}').json_body() == {"a": [1, 2]}
        with pytest.raises(json.JSONDecodeError):
            seen("POST", content=b"{nope").json_body()

    def test_a_body_that_does_not_fit_the_model_is_igni_s_422(self) -> None:
        class Body(BaseModel):
            n: int

        ok = seen("POST", content=b'{"n": 3}').json_model(Body)
        refused = seen("POST", content=b'{"n": "many"}').json_model(Body)
        broken = seen("POST", content=b"not json").json_model(Body)

        assert isinstance(ok, Body) and ok.n == 3
        for answer in (refused, broken):
            assert isinstance(answer, DetailError)
            assert answer.status == 422
            assert answer.detail
        assert isinstance(refused, DetailError) and "n" in refused.detail

    def test_a_form_takes_the_first_value_of_a_repeated_key(self) -> None:
        form = seen("POST", content=b"grant_type=first&grant_type=second&scope=a+b").form()

        assert form.grant_type == "first"
        assert form.scope == "a b"

    def test_a_form_is_decoded_from_percent_escapes_and_unicode(self) -> None:
        form = seen("POST", content=b"token=caf%C3%A9%2B1&organisation=%E2%9C%93").form()

        assert form.token == "café+1"
        assert form.organisation == "✓"

    def test_a_form_with_unknown_keys_and_an_empty_body_still_reads(self) -> None:
        assert seen("POST", content=b"zzz=1").form() == TokenForm()
        assert seen("POST").form() == TokenForm()

    def test_a_form_that_is_not_text_reads_as_a_form_that_proves_nothing(self) -> None:
        form = seen("POST", content=b"grant_type=\xff\xfe&code=ok").form()

        assert form.code == "ok"
        assert not form.is_jwt_bearer

    def test_the_bearer_token_is_what_follows_bearer(self) -> None:
        assert seen(headers={"Authorization": "Bearer abc.def"}).bearer() == "abc.def"

    def test_without_a_bearer_header_the_token_is_empty(self) -> None:
        assert seen().bearer() == ""

    def test_another_scheme_is_left_whole(self) -> None:
        assert (
            seen(headers={"Authorization": "Basic dXNlcjpwdw=="}).bearer() == "Basic dXNlcjpwdw=="
        )

    def test_a_query_parameter_is_its_first_value_or_the_default(self) -> None:
        request = seen(url="http://igni.test/v1/x?limit=5&limit=9&empty=")

        assert request.first("limit") == "5"
        assert request.first("absent") == ""
        assert request.first("absent", "50") == "50"
        # A parameter with no value is not there at all.
        assert request.first("empty", "d") == "d"


class TestTraffic:
    def request(self, path: str) -> httpx.Request:
        return httpx.Request("GET", f"http://igni.test{path}")

    def test_every_request_is_kept_in_order_and_returned_as_read(self) -> None:
        traffic = RecordedTraffic()

        first = traffic.record(self.request("/v1/a"))
        traffic.record(self.request("/v1/b"))

        assert [s.path for s in traffic.seen] == ["/v1/a", "/v1/b"]
        assert traffic.seen[0] is first

    def test_requests_to_matches_the_exact_path_not_a_prefix(self) -> None:
        traffic = RecordedTraffic()
        for path in ("/v1/a", "/v1/a/b", "/v1/ab", "/v1/a"):
            traffic.record(self.request(path))

        assert [s.path for s in traffic.requests_to("/v1/a")] == ["/v1/a", "/v1/a"]
        assert traffic.requests_to("/v1") == []

    def test_nothing_fails_until_asked(self) -> None:
        assert RecordedTraffic().failure_for("/v1/a") is None

    def test_a_prefix_fails_with_igni_failing_on_purpose_until_healed(self) -> None:
        traffic = RecordedTraffic()
        traffic.fail("/v1/a", 503)

        for path in ("/v1/a", "/v1/a/deeper"):
            failure = traffic.failure_for(path)
            assert failure is not None
            assert failure.status_code == 503
            assert failure.json() == {"detail": "failing on purpose"}
        assert traffic.failure_for("/v1/b") is None

        traffic.heal()
        assert traffic.failure_for("/v1/a") is None

    def test_the_first_prefix_asked_for_decides_when_two_cover_a_path(self) -> None:
        traffic = RecordedTraffic()
        traffic.fail("/v1", 500)
        traffic.fail("/v1/a", 502)

        failure = traffic.failure_for("/v1/a")
        assert failure is not None and failure.status_code == 500

    def test_failing_a_prefix_again_changes_its_status(self) -> None:
        traffic = RecordedTraffic()
        traffic.fail("/v1/a", 500)
        traffic.fail("/v1/a", 429)

        failure = traffic.failure_for("/v1/a")
        assert failure is not None and failure.status_code == 429

    def test_heal_keeps_what_was_seen_and_reset_forgets_it_too(self) -> None:
        traffic = RecordedTraffic()
        traffic.record(self.request("/v1/a"))
        traffic.fail("/v1/a", 500)

        traffic.heal()
        assert len(traffic.seen) == 1 and traffic.failing == {}

        traffic.fail("/v1/a", 500)
        traffic.reset()
        assert traffic.seen == [] and traffic.failure_for("/v1/a") is None

    async def test_the_fake_answers_a_failing_path_with_the_status_asked_for(
        self, fake: FakeIgni
    ) -> None:
        fake.traffic.fail(IgniPaths.JWKS, 502)
        async with fake.http_client() as http:
            failing = await http.get(f"{BASE}{IgniPaths.JWKS}")
            fake.traffic.heal()
            healed = await http.get(f"{BASE}{IgniPaths.JWKS}")

        assert failing.status_code == 502
        assert healed.status_code == 200
        assert len(fake.traffic.requests_to(IgniPaths.JWKS)) == 2


async def test_a_token_request_whose_body_is_not_text_is_refused_not_a_crash(
    fake: FakeIgni,
) -> None:
    async with fake.http_client() as http:
        for path in (IgniPaths.TOKEN, IgniPaths.REVOKE):
            answer = await http.post(f"{BASE}{path}", content=b"grant_type=\xff\xfe&token=\x80")
            assert answer.status_code in (400, 401), path
            assert "error" in answer.json()
