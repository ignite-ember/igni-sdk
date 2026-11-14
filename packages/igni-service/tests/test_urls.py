"""A service's URL as igni writes it, and the exact paths igni serves."""

from __future__ import annotations

import pytest

from igni_service.urls import IgniPaths, ServiceUrl


@pytest.mark.parametrize(
    ("given", "written"),
    [
        ("http://service.test", "http://service.test"),
        ("HTTP://Service.TEST/", "http://service.test"),
        ("  https://service.test  ", "https://service.test"),
        ("https://service.test///", "https://service.test"),
        ("http://service.test/", "http://service.test"),
        ("http://service.test:8080", "http://service.test:8080"),
        ("https://service.test:443/", "https://service.test:443"),
        ("http://service.test/Api/V1/", "http://service.test/Api/V1"),
        ("http://service.test/a//", "http://service.test/a"),
        ("http://Service.Test:81/Base", "http://service.test:81/Base"),
        ("http://service.test?", "http://service.test"),
        ("http://service.test#", "http://service.test"),
        ("http://127.0.0.1:9000", "http://127.0.0.1:9000"),
        ("http://user:secret@Service.Test:81/a", "http://service.test:81/a"),
        ("http://service.test/a%20b/", "http://service.test/a%20b"),
    ],
)
def test_a_url_is_written_the_one_way_igni_writes_it(given: str, written: str) -> None:
    assert ServiceUrl.normalise(given) == written
    assert ServiceUrl.normalise(written) == written


@pytest.mark.parametrize(
    ("given", "written"),
    [
        ("http://[::1]", "http://[::1]"),
        ("http://[::1]:8080/", "http://[::1]:8080"),
        ("HTTPS://[2001:DB8::1]:9443/base/", "https://[2001:db8::1]:9443/base"),
    ],
)
def test_an_ipv6_host_keeps_its_brackets_so_the_port_can_be_told_from_the_address(
    given: str, written: str
) -> None:
    assert ServiceUrl.normalise(given) == written
    assert ServiceUrl.normalise(written) == written


@pytest.mark.parametrize(
    "given",
    [
        "",
        "   ",
        "service.test",
        "/just/a/path",
        "//service.test",
        "http://",
        "http:///path",
        "ftp://service.test",
        "ws://service.test",
        "mailto:a@service.test",
        "http://service.test:99999",
        "http://service.test:abc",
    ],
)
def test_what_is_not_an_absolute_http_url_is_refused(given: str) -> None:
    with pytest.raises(ValueError):
        ServiceUrl.normalise(given)


def test_none_is_refused_like_an_empty_url() -> None:
    with pytest.raises(ValueError, match="not an absolute http"):
        ServiceUrl.normalise(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "given",
    [
        "http://service.test/?a=1",
        "http://service.test?a",
        "http://service.test/#top",
        "http://s/p?q#f",
    ],
)
def test_a_query_or_a_fragment_is_refused_and_the_message_names_the_url(given: str) -> None:
    with pytest.raises(ValueError, match="must not have a query or a fragment") as refused:
        ServiceUrl.normalise(given)

    assert repr(given) in str(refused.value)


def test_the_refusal_of_a_non_http_url_names_the_url_as_given() -> None:
    with pytest.raises(ValueError) as refused:
        ServiceUrl.normalise("ftp://Service.test")

    assert str(refused.value) == "'ftp://Service.test' is not an absolute http(s) URL"


def test_every_path_is_spelled_as_igni_serves_it() -> None:
    assert {
        name: value
        for name, value in vars(IgniPaths).items()
        if name.isupper() and isinstance(value, str)
    } == {
        "DISCOVERY": "/.well-known/openid-configuration",
        "JWKS": "/.well-known/jwks.json",
        "CLIENTS": "/v1/clients",
        "TOKEN": "/v1/oauth/token",
        "REVOKE": "/v1/oauth/revoke",
        "DIRECTORY": "/v1/directory",
        "NOTIFICATIONS": "/v1/service-notifications",
        "SERVICE_EVENTS": "/v1/service-events",
        "SERVICE_ITEMS": "/v1/service-items",
        "SERVICE_ATTACHMENTS": "/v1/service-attachments",
        "REVOCATIONS": "/v1/revocations",
        "SERVED": "/v1/organisations/served",
        "SERVICE_VM_PROFILE": "/v1/service-vm-profile",
        "APPS": "/v1/apps",
        "SUBJECTS": "/v1/igni/subjects",
        "ORGANISATIONS": "/v1/igni/organisations",
    }


def test_the_path_builders_put_the_id_where_igni_expects_it() -> None:
    assert IgniPaths.app_vm_profile_request("app-1") == "/v1/apps/app-1/vm-profile-request"
    assert IgniPaths.app_vm_profile("app-1") == "/v1/apps/app-1/vm-profile"
    assert IgniPaths.service_event("evt-9") == "/v1/service-events/evt-9"
    assert IgniPaths.extension("cli-3") == "/v1/clients/cli-3/extension"
    assert IgniPaths.extension_asset("cli-3", "ab12") == "/v1/clients/cli-3/extension/assets/ab12"
