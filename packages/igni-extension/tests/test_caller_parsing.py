"""`Caller`, `RequestMeta` and `CallerScope` without a server: what each makes of what it is given.

test_caller.py serves real calls; these are the edges of the pieces that
read the wire and wrap a handler.
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from igni_extension import Caller, CallerKind, NoCaller
from igni_extension.caller import _META, _SCOPE, CallerScope, RequestMeta

ADA = {"kind": "person", "id": "u-ada", "org": "org-acme", "group": "g-legal"}
SPACE = {
    "kind": "space",
    "id": "sp-1",
    "org": "org-acme",
    "app": "app-notes",
    "external_id": "end-user-7",
}


class TestOf:
    def test_a_person_is_read_with_everything_the_host_sent(self) -> None:
        caller = Caller.of({**ADA, "session": "s-1"})

        assert caller == Caller(
            kind=CallerKind.PERSON, id="u-ada", org="org-acme", group="g-legal", session="s-1"
        )

    def test_a_space_carries_its_app_and_its_end_user(self) -> None:
        caller = Caller.of(SPACE)

        assert caller is not None
        assert caller.kind is CallerKind.SPACE and str(caller.kind) == "space"
        assert (caller.app, caller.external_id) == ("app-notes", "end-user-7")
        assert caller.group is None

    def test_a_person_and_an_app_have_no_app_or_end_user(self) -> None:
        for kind in ("person", "app"):
            caller = Caller.of({"kind": kind, "id": "x"})

            assert caller is not None
            assert (caller.app, caller.external_id) == (None, None)

    @pytest.mark.parametrize("raw", [None, "person:u-ada", ["kind", "id"], 7, b"{}", (), True])
    def test_what_is_not_a_dict_is_no_caller(self, raw: Any) -> None:
        assert Caller.of(raw) is None

    @pytest.mark.parametrize(
        "raw",
        [
            {},
            {"kind": "person"},
            {"id": "u-ada"},
            {"kind": "robot", "id": "x"},
            {"kind": "person", "id": 7},
            {"kind": 1, "id": "x"},
            {"kind": "person", "id": None},
            {"kind": "person", "id": "x", "org": ["a"]},
            {"kind": "PERSON", "id": "x"},
        ],
    )
    def test_a_malformed_principal_is_no_caller_and_never_raises(self, raw: dict[str, Any]) -> None:
        assert Caller.of(raw) is None

    def test_a_field_this_sdk_does_not_know_yet_is_ignored(self) -> None:
        caller = Caller.of({**ADA, "tenant_tier": "gold"})

        assert caller == Caller.of(ADA)

    def test_an_empty_id_is_still_a_caller(self) -> None:
        caller = Caller.of({"kind": "app", "id": ""})

        assert caller is not None and caller.ref == "app:"


class TestCaller:
    def test_its_ref_is_kind_and_id(self) -> None:
        assert Caller(kind=CallerKind.PERSON, id="u-ada").ref == "person:u-ada"
        assert Caller(kind=CallerKind.APP, id="app-1").ref == "app:app-1"
        assert Caller(kind=CallerKind.SPACE, id="sp-1").ref == "space:sp-1"

    def test_an_id_with_a_colon_or_unicode_is_kept_whole(self) -> None:
        assert Caller(kind=CallerKind.SPACE, id="a:b:Ünï").ref == "space:a:b:Ünï"

    def test_it_is_frozen(self) -> None:
        caller = Caller(kind=CallerKind.PERSON, id="u-ada")

        with pytest.raises(ValidationError):
            caller.id = "u-grace"

    def test_the_kinds_are_the_three_strings_the_host_sends(self) -> None:
        assert {kind.name: kind.value for kind in CallerKind} == {
            "PERSON": "person",
            "APP": "app",
            "SPACE": "space",
        }

    def test_the_wire_names_are_what_the_host_uses(self) -> None:
        assert Caller.META_KEY == "igni/principal"
        assert Caller.TOKEN_HEADER == "X-Igni-Principal"  # noqa: S105


class TestCurrent:
    def test_outside_any_call_there_is_none_and_required_says_so(self) -> None:
        assert Caller.current() is None
        with pytest.raises(NoCaller, match="no caller"):
            Caller.required()

    def test_the_scope_wins_over_the_request_meta(self) -> None:
        meta = {Caller.META_KEY: ADA}
        grace = Caller(kind=CallerKind.PERSON, id="u-grace")
        token = _META.set(meta)
        try:
            assert Caller.current() == Caller.of(ADA)
            with CallerScope.of(grace):
                assert Caller.current() == grace
                assert Caller.required() == grace
            assert Caller.current() == Caller.of(ADA)
        finally:
            _META.reset(token)

    def test_a_meta_without_a_principal_or_with_a_bad_one_is_no_caller(self) -> None:
        for meta in ({}, {"other": 1}, {Caller.META_KEY: "u-ada"}, {Caller.META_KEY: {"id": "x"}}):
            token = _META.set(meta)
            try:
                assert Caller.current() is None
            finally:
                _META.reset(token)

    def test_scopes_nest_and_restore_even_when_the_block_raises(self) -> None:
        ada = Caller(kind=CallerKind.PERSON, id="u-ada")
        grace = Caller(kind=CallerKind.PERSON, id="u-grace")

        with CallerScope.of(ada):
            with pytest.raises(RuntimeError), CallerScope.of(grace):
                assert Caller.current() == grace
                raise RuntimeError("boom")
            assert Caller.current() == ada
        assert Caller.current() is None
        assert _SCOPE.get() is None

    def test_a_scope_of_none_hides_nothing_outside_it(self) -> None:
        with CallerScope.of(None):
            assert Caller.current() is None


class TestRequestMeta:
    @staticmethod
    async def _serve(meta: Any, seen: list[Any], *, raises: bool = False) -> Any:
        async def call_next(ctx: Any) -> str:
            seen.append(RequestMeta.current())
            await asyncio.sleep(0)
            seen.append(RequestMeta.current())
            if raises:
                raise ValueError("the handler failed")
            return "result"

        return await RequestMeta.middleware(SimpleNamespace(meta=meta), call_next)  # type: ignore[arg-type]

    async def test_the_requests_meta_is_current_while_it_is_served_and_gone_after(self) -> None:
        seen: list[Any] = []

        assert await self._serve({"a": 1}, seen) == "result"

        assert seen == [{"a": 1}, {"a": 1}]
        assert RequestMeta.current() is None

    async def test_it_is_reset_after_a_handler_that_raises(self) -> None:
        seen: list[Any] = []

        with pytest.raises(ValueError, match="the handler failed"):
            await self._serve({"a": 1}, seen, raises=True)

        assert RequestMeta.current() is None

    @pytest.mark.parametrize("meta", [None, {}])
    async def test_a_request_without_meta_has_none(self, meta: Any) -> None:
        seen: list[Any] = []

        await self._serve(meta, seen)

        assert seen == [None, None]

    async def test_the_meta_is_a_copy_the_handler_cannot_use_to_change_the_request(self) -> None:
        original = {"a": 1}
        seen: list[Any] = []

        await self._serve(original, seen)

        assert seen[0] == original and seen[0] is not original

    async def test_concurrent_requests_each_see_their_own(self) -> None:
        seen_a: list[Any] = []
        seen_b: list[Any] = []

        await asyncio.gather(self._serve({"r": "a"}, seen_a), self._serve({"r": "b"}, seen_b))

        assert seen_a == [{"r": "a"}] * 2
        assert seen_b == [{"r": "b"}] * 2


# Defined with real annotations: `inject` reads them, and a few tests need ones that cannot resolve.


def _plain(x: int) -> int:
    return x


def _first(caller: Caller, x: int = 1) -> tuple[Caller, int]:
    return caller, x


def _optional_sync(x: int, caller: Caller | None = None) -> tuple[int, Caller | None]:
    return x, caller


async def _optional_async(caller: Caller | None) -> Caller | None:
    return caller


def _two(first: Caller, second: Caller) -> tuple[Caller, Caller]:
    return first, second


def _returns_a_caller(x: int) -> Caller:
    return Caller(kind=CallerKind.APP, id=str(x))


class TestScopeParameters:
    def test_the_parameter_typed_caller_is_found_by_name(self) -> None:
        assert CallerScope.parameter(_first) == "caller"
        assert CallerScope.parameter(_optional_sync) == "caller"
        assert CallerScope.parameter(_optional_async) == "caller"

    def test_a_function_without_one_has_none_and_a_return_annotation_is_not_one(self) -> None:
        assert CallerScope.parameter(_plain) is None
        assert CallerScope.parameter(_returns_a_caller) is None

    def test_annotations_that_cannot_be_resolved_fall_back_to_the_raw_ones(self) -> None:
        def handler(who, other):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN202
            return who, other

        handler.__annotations__ = {"who": Caller, "other": "NotDefinedAnywhere"}

        assert CallerScope.parameter(handler) == "who"
        assert CallerScope.optional(handler, "who") is False

    def test_only_caller_or_none_is_optional(self) -> None:
        assert CallerScope.optional(_optional_sync, "caller") is True
        assert CallerScope.optional(_first, "caller") is False
        assert CallerScope.optional(_first, "x") is False
        assert CallerScope.optional(_first, "missing") is False


class TestInject:
    def test_a_function_without_a_caller_parameter_comes_back_untouched(self) -> None:
        assert CallerScope.inject(_plain) is _plain

    def test_the_wrapper_hides_the_caller_from_its_signature_and_annotations(self) -> None:
        wrapped = CallerScope.inject(_first)

        assert list(inspect.signature(wrapped).parameters) == ["x"]
        assert inspect.signature(wrapped).parameters["x"].annotation is int
        assert "caller" not in wrapped.__annotations__
        assert wrapped.__annotations__["x"] is int
        assert wrapped.__name__ == "_first"
        assert not hasattr(wrapped, "__wrapped__")

    def test_a_return_annotation_naming_caller_is_kept(self) -> None:
        wrapped = CallerScope.inject(_first)

        assert inspect.signature(wrapped).return_annotation == tuple[Caller, int]

    def test_a_sync_function_is_handed_its_caller_and_stays_sync(self) -> None:
        wrapped = CallerScope.inject(_first)
        ada = Caller.of(ADA)

        with CallerScope.of(ada):
            assert wrapped(5) == (ada, 5)
        assert not inspect.iscoroutinefunction(wrapped)

    def test_a_sync_function_that_needs_a_caller_fails_without_one(self) -> None:
        with pytest.raises(NoCaller):
            CallerScope.inject(_first)(1)

    def test_an_optional_caller_on_a_sync_function_is_none_without_one(self) -> None:
        wrapped = CallerScope.inject(_optional_sync)

        assert wrapped(3) == (3, None)
        with CallerScope.of(Caller.of(ADA)):
            assert wrapped(3) == (3, Caller.of(ADA))

    async def test_an_async_function_is_handed_its_caller_and_stays_a_coroutine(self) -> None:
        wrapped = CallerScope.inject(_optional_async)

        assert inspect.iscoroutinefunction(wrapped)
        assert await wrapped() is None
        with CallerScope.of(Caller.of(SPACE)):
            assert await wrapped() == Caller.of(SPACE)

    def test_only_the_first_caller_parameter_is_filled(self) -> None:
        wrapped = CallerScope.inject(_two)

        assert list(inspect.signature(wrapped).parameters) == ["second"]
        with CallerScope.of(Caller.of(ADA)), pytest.raises(TypeError):
            wrapped()  # `second` is still the author's to pass: it was not injected

    def test_positional_arguments_after_the_caller_land_on_their_own_parameters(self) -> None:
        def middle(a: int, caller: Caller, b: int, *, c: int = 0) -> tuple[int, Caller, int, int]:
            return a, caller, b, c

        wrapped = CallerScope.inject(middle)
        ada = Caller.of(ADA)

        with CallerScope.of(ada):
            assert wrapped(1, 2) == (1, ada, 2, 0)
            assert wrapped(1, b=2, c=3) == (1, ada, 2, 3)
            assert wrapped(a=1, b=2) == (1, ada, 2, 0)

    def test_a_keyword_only_caller_is_passed_by_name(self) -> None:
        def only(a: int, *, caller: Caller) -> tuple[int, Caller]:
            return a, caller

        ada = Caller.of(ADA)

        with CallerScope.of(ada):
            assert CallerScope.inject(only)(4) == (4, ada)


class TestNoCallerMessage:
    def test_it_says_no_caller_means_the_signed_in_person_not_the_extension(self) -> None:
        with pytest.raises(NoCaller) as raised:
            Caller.required()
        message = str(raised.value)
        assert "as the signed-in person" in message
        assert "extension itself" not in message
