"""ServiceUrl and IgniPaths: the one spelling of a service's URL and the paths igni serves."""

from __future__ import annotations

import pytest

from igni_service.urls import IgniPaths, ServiceUrl


class TestAServiceUrlIsWrittenTheWayIgniWritesIt:
    @pytest.mark.parametrize(
        ("given", "written"),
        [
            ("https://service.test", "https://service.test"),
            ("https://service.test/", "https://service.test"),
            ("HTTPS://Service.TEST", "https://service.test"),
            ("  https://service.test  ", "https://service.test"),
            ("http://service.test:8080/", "http://service.test:8080"),
            ("https://service.test:443", "https://service.test:443"),
            ("https://service.test/app/", "https://service.test/app"),
            ("https://service.test/app///", "https://service.test/app"),
            ("https://service.test/a//b/", "https://service.test/a//b"),
            ("https://service.test/Path", "https://service.test/Path"),
            ("http://127.0.0.1:9000/x", "http://127.0.0.1:9000/x"),
        ],
    )
    def test_scheme_and_host_lower_case_no_trailing_slash(self, given: str, written: str) -> None:
        assert ServiceUrl.normalise(given) == written

    def test_user_and_password_are_not_part_of_it(self) -> None:
        assert ServiceUrl.normalise("https://user:pw@Service.test:81/x") == (
            "https://service.test:81/x"
        )

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "   ",
            "service.test",
            "/relative/path",
            "ftp://service.test",
            "javascript:alert(1)",
            "file:///etc/passwd",
            "https://",
            "https:///path",
            "//service.test",
        ],
    )
    def test_anything_but_an_absolute_http_url_is_refused(self, url: str) -> None:
        with pytest.raises(ValueError, match="is not an absolute http"):
            ServiceUrl.normalise(url)

    def test_nothing_is_not_an_url(self) -> None:
        with pytest.raises(ValueError, match="is not an absolute http"):
            ServiceUrl.normalise(None)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "url",
        [
            "https://service.test?x=1",
            "https://service.test/?",
            "https://service.test/#top",
            "https://service.test/app?x=1#top",
            "https://service.test#",
        ],
    )
    def test_a_query_or_a_fragment_is_refused(self, url: str) -> None:
        if url.endswith(("?", "#")):
            # urlsplit drops an empty query or fragment: it is no query at all.
            assert ServiceUrl.normalise(url) == url.rstrip("?#").rstrip("/")
            return
        with pytest.raises(ValueError, match="must not have a query or a fragment"):
            ServiceUrl.normalise(url)

    @pytest.mark.parametrize("url", ["https://service.test:abc", "https://service.test:99999"])
    def test_a_port_that_is_not_one_is_a_value_error(self, url: str) -> None:
        with pytest.raises(ValueError, match="Port"):
            ServiceUrl.normalise(url)


class TestThePathsTheWireFixes:
    @pytest.mark.parametrize(
        ("name", "path"),
        [
            ("DISCOVERY", "/.well-known/openid-configuration"),
            ("JWKS", "/.well-known/jwks.json"),
            ("CLIENTS", "/v1/clients"),
            ("TOKEN", "/v1/oauth/token"),
            ("REVOKE", "/v1/oauth/revoke"),
            ("DIRECTORY", "/v1/directory"),
            ("NOTIFICATIONS", "/v1/service-notifications"),
            ("SERVICE_EVENTS", "/v1/service-events"),
            ("SERVICE_ITEMS", "/v1/service-items"),
            ("SERVICE_ATTACHMENTS", "/v1/service-attachments"),
            ("REVOCATIONS", "/v1/revocations"),
            ("SERVED", "/v1/organisations/served"),
            ("SERVICE_VM_PROFILE", "/v1/service-vm-profile"),
            ("APPS", "/v1/apps"),
            ("SUBJECTS", "/v1/igni/subjects"),
            ("ORGANISATIONS", "/v1/igni/organisations"),
        ],
    )
    def test_every_constant_is_the_path_igni_serves(self, name: str, path: str) -> None:
        assert getattr(IgniPaths, name) == path

    def test_no_constant_is_missing_or_added_unnoticed(self) -> None:
        names = {n for n in vars(IgniPaths) if n.isupper()}

        assert len(names) == 16

    def test_the_builders_put_the_id_where_igni_reads_it(self) -> None:
        assert IgniPaths.app_vm_profile_request("app-1") == "/v1/apps/app-1/vm-profile-request"
        assert IgniPaths.app_vm_profile("app-1") == "/v1/apps/app-1/vm-profile"
        assert IgniPaths.service_event("evt-9") == "/v1/service-events/evt-9"
        assert IgniPaths.extension("client-7") == "/v1/clients/client-7/extension"
        assert IgniPaths.extension_asset("client-7", "ab12") == (
            "/v1/clients/client-7/extension/assets/ab12"
        )

    def test_an_ordinary_id_is_sent_as_it_is(self) -> None:
        ordinary = "Ab-9_x.y~z"

        assert IgniPaths.app_vm_profile(ordinary) == f"/v1/apps/{ordinary}/vm-profile"
