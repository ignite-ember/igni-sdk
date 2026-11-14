"""An IPv6 host is written with its brackets: without them the URL names another host."""

from __future__ import annotations

import pytest

from igni_service.urls import ServiceUrl


class TestAnIpv6Host:
    @pytest.mark.parametrize(
        ("given", "written"),
        [
            ("http://[::1]:8080/x", "http://[::1]:8080/x"),
            ("https://[::1]/", "https://[::1]"),
            ("https://[2001:DB8::1]:9443", "https://[2001:db8::1]:9443"),
        ],
    )
    def test_an_ipv6_host_keeps_its_brackets(self, given: str, written: str) -> None:
        assert ServiceUrl.normalise(given) == written
