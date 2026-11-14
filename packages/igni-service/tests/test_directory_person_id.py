"""A member's id in the directory path: one escaped segment, and a blank one is nobody."""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest

from igni_service import IgniService
from igni_service.directory import DirectoryClient
from igni_service.service_tokens import ServiceTokens
from igni_service.urls import IgniPaths

from .conftest import ORG

PEOPLE = f"{IgniPaths.DIRECTORY}/people"


class Asked:
    """Stands in for `ServiceTokens`: answers every request with `response` and keeps them."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.calls: list[str] = []

    async def request(
        self, method: str, path: str, *, org_id: str, **kwargs: Any
    ) -> httpx.Response:
        self.calls.append(path)
        return self.response

    def client(self) -> DirectoryClient:
        return DirectoryClient(cast(ServiceTokens, self))


class TestAPersonsId:
    """The id is one path segment; it is not allowed to address anything else."""

    @pytest.mark.parametrize("user_id", ["", "   "])
    async def test_a_blank_id_is_nobody_and_asks_nothing(self, user_id: str) -> None:
        asked = Asked(httpx.Response(200, json={"user_id": "x"}))

        assert await asked.client().person(ORG, user_id) is None
        assert asked.calls == []

    @pytest.mark.parametrize(
        ("user_id", "path"),
        [
            ("u-1", f"{PEOPLE}/u-1"),
            ("../members", f"{PEOPLE}/..%2Fmembers"),
            ("u-1?include_former=true", f"{PEOPLE}/u-1%3Finclude_former%3Dtrue"),
            ("a/b", f"{PEOPLE}/a%2Fb"),
            ("u#1", f"{PEOPLE}/u%231"),
            ("ü 1", f"{PEOPLE}/%C3%BC%201"),
        ],
    )
    async def test_the_id_is_one_escaped_path_segment(self, user_id: str, path: str) -> None:
        asked = Asked(httpx.Response(404))

        assert await asked.client().person(ORG, user_id) is None

        assert asked.calls == [path]

    async def test_an_id_with_a_question_mark_does_not_find_the_member_before_it(
        self, igni: IgniService
    ) -> None:
        assert await igni.host(ORG).directory.person("u-max?x=1") is None
        assert (await igni.host(ORG).directory.person("u-max")) is not None
