"""Erasure and export at their edges: no such person, odd ids, repeats, replaced handlers, bad rows."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx
import pytest
from pydantic import ValidationError

from igni_service import ExportSection, IgniService, Subject
from igni_service.subjects import SubjectExport, SubjectHandlers
from igni_service.testing import FakeIgni
from igni_service.urls import IgniPaths

from .conftest import ORG, OTHER_ORG, bearer


def igni_headers(fake: FakeIgni, org: str = ORG) -> dict[str, str]:
    return bearer(fake.signer.igni_token(org))


class TestTheHandlersAreRegisteredByDecorator:
    def test_a_decorator_hands_the_handler_back_unchanged(self) -> None:
        handlers = SubjectHandlers()

        async def erase(subject: Subject) -> None: ...

        async def export(subject: Subject) -> list[ExportSection]:
            return []

        assert handlers.on_erase(erase) is erase
        assert handlers.on_export(export) is export
        assert (handlers.erase, handlers.export) == (erase, export)

    def test_none_is_registered_until_one_is(self) -> None:
        handlers = SubjectHandlers()

        assert (handlers.erase, handlers.export) == (None, None)

    async def test_a_later_registration_replaces_the_earlier_one(
        self, igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient
    ) -> None:
        calls: list[str] = []

        @igni.on_erase
        async def first(subject: Subject) -> None:
            calls.append("first")

        @igni.on_erase
        async def second(subject: Subject) -> None:
            calls.append("second")

        await http.delete("/v1/igni/subjects/u-max", headers=igni_headers(fake))

        assert calls == ["second"]


class TestErasure:
    async def test_it_is_idempotent_204_each_time(
        self, igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient
    ) -> None:
        erased: list[str] = []

        @igni.on_erase
        async def erase(subject: Subject) -> None:
            erased.append(subject.user_id)

        first = await http.delete("/v1/igni/subjects/u-max", headers=igni_headers(fake))
        again = await http.delete("/v1/igni/subjects/u-max", headers=igni_headers(fake))

        assert (first.status_code, again.status_code) == (204, 204)
        assert first.content == again.content == b""
        assert erased == ["u-max", "u-max"]

    async def test_a_person_the_directory_does_not_know_is_erased_by_id_with_no_member(
        self, igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient
    ) -> None:
        erased: list[Subject] = []

        @igni.on_erase
        async def erase(subject: Subject) -> None:
            erased.append(subject)

        response = await http.delete("/v1/igni/subjects/u-nobody", headers=igni_headers(fake))

        assert response.status_code == 204
        assert erased == [Subject(user_id="u-nobody", org_id=ORG, email="", name="", member=None)]

    async def test_a_former_member_is_found_with_their_entry(
        self, igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient
    ) -> None:
        erased: list[Subject] = []

        @igni.on_erase
        async def erase(subject: Subject) -> None:
            erased.append(subject)

        await http.delete("/v1/igni/subjects/u-gone", headers=igni_headers(fake))

        [subject] = erased
        assert subject.member is not None and subject.member.status == "deactivated"
        assert (subject.email, subject.name) == ("gone@acme.test", "Gone Person")

    async def test_the_organisation_is_the_tokens_and_a_person_of_another_is_not_found_there(
        self, igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient
    ) -> None:
        erased: list[Subject] = []

        @igni.on_erase
        async def erase(subject: Subject) -> None:
            erased.append(subject)

        await http.delete(
            "/v1/igni/subjects/u-eve", headers=igni_headers(fake, ORG), params={"org": OTHER_ORG}
        )
        await http.delete("/v1/igni/subjects/u-eve", headers=igni_headers(fake, OTHER_ORG))

        assert [(s.org_id, s.email) for s in erased] == [(ORG, ""), (OTHER_ORG, "eve@other.test")]

    @pytest.mark.parametrize("user_id", ["u-ünï-名前", "u with space", "u?x=1", "u#frag", "u%20x"])
    async def test_an_id_with_unicode_or_url_special_characters_reaches_the_handler_whole(
        self, igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient, user_id: str
    ) -> None:
        erased: list[str] = []

        @igni.on_erase
        async def erase(subject: Subject) -> None:
            erased.append(subject.user_id)

        response = await http.delete(
            f"/v1/igni/subjects/{quote(user_id, safe='')}", headers=igni_headers(fake)
        )

        assert response.status_code == 204
        assert erased == [user_id]

    async def test_an_id_with_a_slash_is_not_a_subject_route(
        self, igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient
    ) -> None:
        @igni.on_erase
        async def erase(subject: Subject) -> None:
            raise AssertionError("must not be reached")

        response = await http.delete("/v1/igni/subjects/a/b", headers=igni_headers(fake))

        assert response.status_code in (404, 405)

    async def test_a_directory_that_is_away_is_said_in_a_warning_and_the_erasure_goes_on(
        self,
        igni: IgniService,
        fake: FakeIgni,
        http: httpx.AsyncClient,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        @igni.on_erase
        async def erase(subject: Subject) -> None: ...

        fake.traffic.fail(IgniPaths.DIRECTORY, 503)
        with caplog.at_level(logging.WARNING, logger="igni_service.subjects"):
            response = await http.delete("/v1/igni/subjects/u-max", headers=igni_headers(fake))

        assert response.status_code == 204
        [record] = [r for r in caplog.records if r.name == "igni_service.subjects"]
        assert record.levelno == logging.WARNING
        assert "could not look up the subject" in record.getMessage()
        assert "going by id alone" in record.getMessage()

    async def test_a_handler_that_fails_is_not_answered_as_an_erasure(
        self, igni: IgniService, fake: FakeIgni, app: Any
    ) -> None:
        @igni.on_erase
        async def erase(subject: Subject) -> None:
            raise RuntimeError("the database is gone")

        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://service.test") as http:
            response = await http.delete("/v1/igni/subjects/u-max", headers=igni_headers(fake))

        assert response.status_code == 500, "igni then repeats it: nothing says it was erased"


class TestExport:
    @pytest.fixture
    def export_with(self, igni: IgniService) -> Callable[[Any], None]:
        def register(result: Any) -> None:
            @igni.on_export
            async def export(subject: Subject) -> Any:
                return result

        return register

    async def test_a_handler_with_nothing_to_say_answers_no_sections(
        self,
        export_with: Callable[[Any], None],
        fake: FakeIgni,
        http: httpx.AsyncClient,
    ) -> None:
        export_with([])

        response = await http.get("/v1/igni/subjects/u-max/export", headers=igni_headers(fake))

        assert (response.status_code, response.json()) == (200, {"sections": []})

    async def test_a_section_with_no_rows_is_kept_with_an_empty_list(
        self,
        export_with: Callable[[Any], None],
        fake: FakeIgni,
        http: httpx.AsyncClient,
    ) -> None:
        export_with([ExportSection(name="Notes")])

        response = await http.get("/v1/igni/subjects/u-max/export", headers=igni_headers(fake))

        assert response.json() == {"sections": [{"name": "Notes", "rows": []}]}

    async def test_a_handler_may_answer_any_iterable_of_sections(
        self,
        export_with: Callable[[Any], None],
        fake: FakeIgni,
        http: httpx.AsyncClient,
    ) -> None:
        export_with(ExportSection(name=n) for n in ("A", "B"))

        response = await http.get("/v1/igni/subjects/u-max/export", headers=igni_headers(fake))

        assert [s["name"] for s in response.json()["sections"]] == ["A", "B"]

    async def test_every_scalar_cell_is_kept_as_it_is(
        self,
        export_with: Callable[[Any], None],
        fake: FakeIgni,
        http: httpx.AsyncClient,
    ) -> None:
        row: dict[str, Any] = {"s": "text", "i": 3, "f": 1.5, "b": True, "n": None}
        export_with([ExportSection.model_validate({"name": "Cells", "rows": [row]})])

        response = await http.get("/v1/igni/subjects/u-max/export", headers=igni_headers(fake))

        assert response.json()["sections"][0]["rows"] == [row]

    def test_a_cell_that_is_not_a_scalar_is_not_an_export_row(self) -> None:
        for cell in ([1], {"a": 1}):
            with pytest.raises(ValidationError):
                ExportSection.model_validate({"name": "Bad", "rows": [{"c": cell}]})

    def test_a_section_needs_a_name_and_an_export_defaults_to_no_sections(self) -> None:
        with pytest.raises(ValidationError):
            ExportSection.model_validate({"rows": []})
        assert SubjectExport().sections == []

    async def test_the_export_is_of_the_person_in_the_tokens_organisation(
        self, igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient
    ) -> None:
        @igni.on_export
        async def export(subject: Subject) -> list[ExportSection]:
            return [ExportSection(name=subject.org_id, rows=[{"who": subject.email}])]

        mine = await http.get("/v1/igni/subjects/u-eve/export", headers=igni_headers(fake, ORG))
        theirs = await http.get(
            "/v1/igni/subjects/u-eve/export", headers=igni_headers(fake, OTHER_ORG)
        )

        assert mine.json()["sections"] == [{"name": ORG, "rows": [{"who": ""}]}]
        assert theirs.json()["sections"] == [
            {"name": OTHER_ORG, "rows": [{"who": "eve@other.test"}]}
        ]

    async def test_only_igni_may_export(
        self, igni: IgniService, fake: FakeIgni, http: httpx.AsyncClient
    ) -> None:
        @igni.on_export
        async def export(subject: Subject) -> list[ExportSection]:
            raise AssertionError("must not be reached")

        person = bearer(fake.signer.person_token("u-ada", org_id=ORG))

        assert (await http.get("/v1/igni/subjects/u-max/export", headers=person)).status_code == 401
        assert (await http.get("/v1/igni/subjects/u-max/export")).status_code == 401

    async def test_the_501_names_what_is_missing(
        self, fake: FakeIgni, http: httpx.AsyncClient
    ) -> None:
        erase = await http.delete("/v1/igni/subjects/u-max", headers=igni_headers(fake))
        export = await http.get("/v1/igni/subjects/u-max/export", headers=igni_headers(fake))

        assert erase.json() == {"detail": "This service has no erasure handler."}
        assert export.json() == {"detail": "This service has no export handler."}


def test_a_subject_is_frozen_and_empty_where_the_directory_was_not_asked() -> None:
    subject = Subject(user_id="u", org_id="o")

    assert (subject.email, subject.name, subject.member) == ("", "", None)
    with pytest.raises(ValidationError):
        subject.email = "x"
