"""An id given to a path builder is one path segment, whatever it holds."""

from __future__ import annotations

import httpx
import pytest

from igni_service.urls import IgniPaths

SEGMENTS = {
    "../x": "..%2Fx",
    "a/b": "a%2Fb",
    "a?b=1": "a%3Fb%3D1",
    "a#b": "a%23b",
    "a b": "a%20b",
    "..": "%2E%2E",
    ".": "%2E",
    "%2e%2e": "%252e%252e",
}


@pytest.mark.parametrize("hostile", SEGMENTS)
class TestAnIdIsOneSegment:
    def test_the_builders_escape_it(self, hostile: str) -> None:
        segment = SEGMENTS[hostile]

        assert IgniPaths.app_vm_profile_request(hostile) == f"/v1/apps/{segment}/vm-profile-request"
        assert IgniPaths.app_vm_profile(hostile) == f"/v1/apps/{segment}/vm-profile"
        assert IgniPaths.service_event(hostile) == f"/v1/service-events/{segment}"
        assert IgniPaths.extension(hostile) == f"/v1/clients/{segment}/extension"
        assert IgniPaths.extension_asset(hostile, hostile) == (
            f"/v1/clients/{segment}/extension/assets/{segment}"
        )

    def test_the_request_goes_where_the_path_says(self, hostile: str) -> None:
        url = httpx.URL("http://igni.test" + IgniPaths.app_vm_profile(hostile))

        assert url.raw_path == f"/v1/apps/{SEGMENTS[hostile]}/vm-profile".encode()


def test_a_hostile_digest_or_client_id_is_one_segment_too() -> None:
    path = IgniPaths.extension_asset("c/../x", "a?b")

    assert path == "/v1/clients/c%2F..%2Fx/extension/assets/a%3Fb"
