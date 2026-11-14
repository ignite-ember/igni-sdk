"""What igni-client raises on purpose, and how igni's sentences are told apart."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from igni_client import (
    AccessRefused,
    ApprovalRequired,
    AuthError,
    IgniClientError,
    InvalidArguments,
    MethodFailed,
    NotAllowed,
    NotSupported,
    RpcError,
    RunFailed,
    RunInterrupted,
    Unavailable,
    UnexpectedAnswer,
    UnknownMethod,
)
from igni_client.errors import _BY_CODE, _REFUSALS
from igni_client.models import Requirement


def _requirement(tool: str, friendly: str = "") -> Requirement:
    return Requirement.model_validate(
        {
            "requirement_id": f"r-{tool}",
            "tool_name": tool,
            "friendly_name": friendly,
            "tool_args": {},
            "description": "",
        }
    )


def test_an_rpc_error_reads_method_then_message_and_keeps_both() -> None:
    error = RpcError("get_todos", "the disk is full")

    assert str(error) == "get_todos: the disk is full"
    assert (error.method, error.message) == ("get_todos", "the disk is full")
    assert RpcError("", "").method == "" and str(RpcError("m", "ünï ✓")) == "m: ünï ✓"


@pytest.mark.parametrize("marker", _REFUSALS)
def test_each_refusal_igni_words_is_an_access_refusal(marker: str) -> None:
    error = RpcError.of("some_method", f"some_method: {marker}, sorry")

    assert type(error) is AccessRefused
    assert isinstance(error, NotAllowed) and isinstance(error, RpcError)


def test_the_refusal_markers_are_the_four_sentences_igni_says() -> None:
    assert _REFUSALS == (
        "only igni's window",
        "a program answers approval requests only with an approver token",
        "only on the platform's control connection",
        "an approver answers once",
    )


def test_a_refusal_anywhere_in_the_sentence_wins_over_the_other_kinds() -> None:
    assert type(RpcError.of("m", "Unknown RPC method: only igni's window")) is AccessRefused
    assert (
        type(RpcError.of("m", "m: 'x' only igni's window is a required argument")) is AccessRefused
    )


def test_an_unknown_method_is_told_by_the_start_of_the_sentence() -> None:
    error = RpcError.of("get_todos", "Unknown RPC method: get_todos")

    assert type(error) is UnknownMethod and error.method == "get_todos"
    assert type(RpcError.of("m", "it said Unknown RPC method")) is MethodFailed


def test_a_missing_argument_and_a_pydantic_refusal_are_invalid_arguments() -> None:
    missing = RpcError.of("read_process_tail", "pid is a required argument")
    pydantic_style = RpcError.of("read_process_tail", "read_process_tail: 'abc' is not an int")

    for error in (missing, pydantic_style):
        assert type(error) is InvalidArguments
        assert isinstance(error, ValueError) and isinstance(error, RpcError)
    assert type(RpcError.of("m", "other: 'x' is odd")) is MethodFailed
    assert type(RpcError.of("m", "is a required argument, they said")) is MethodFailed


@pytest.mark.parametrize("message", ["the disk is full", "", "ünï ✓ failed"])
def test_any_other_sentence_is_a_method_failure_with_igni_s_words(message: str) -> None:
    error = RpcError.of("m", message)

    assert type(error) is MethodFailed and error.message == message and error.method == "m"
    assert not isinstance(error, (NotAllowed, ValueError))


def test_every_error_is_an_igni_client_error_and_the_kinds_stay_apart() -> None:
    for kind in (
        Unavailable,
        AuthError,
        NotAllowed,
        NotSupported,
        RpcError,
        RunFailed,
        RunInterrupted,
        ApprovalRequired,
    ):
        assert issubclass(kind, IgniClientError)
    assert issubclass(UnexpectedAnswer, RpcError) and not issubclass(UnexpectedAnswer, ValueError)
    assert not issubclass(Unavailable, NotAllowed) and not issubclass(AuthError, NotAllowed)
    assert not issubclass(UnknownMethod, NotAllowed)


def test_an_approval_required_names_the_tools_it_waits_for() -> None:
    both = ApprovalRequired([_requirement("shell", "Run a command"), _requirement("write")])
    none = ApprovalRequired([])

    assert str(both) == "the run is waiting for approval of Run a command, write"
    assert str(none) == "the run is waiting for approval of a tool" and none.requirements == []
    assert [r.tool_name for r in both.requirements] == ["shell", "write"]


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        ("forbidden", AccessRefused),
        ("unknown_method", UnknownMethod),
        ("invalid", InvalidArguments),
        ("not_found", MethodFailed),
        ("refused", MethodFailed),
        ("unavailable", MethodFailed),
        ("cancelled", MethodFailed),
        ("failed", MethodFailed),
    ],
)
def test_a_code_decides_the_kind_whatever_the_sentence_says(code: str, kind: type) -> None:
    error = RpcError.of("m", "igni reworded this entirely", code)

    assert type(error) is kind and error.message == "igni reworded this entirely"


def test_the_code_wins_over_a_sentence_that_says_something_else() -> None:
    assert type(RpcError.of("m", "only igni's window", "failed")) is MethodFailed
    assert type(RpcError.of("m", "Unknown RPC method: m", "forbidden")) is AccessRefused


def test_a_reply_with_no_code_is_still_read_from_its_sentence() -> None:
    assert type(RpcError.of("m", "m: only igni's window may", None)) is AccessRefused
    assert type(RpcError.of("m", "Unknown RPC method: m", None)) is UnknownMethod
    assert type(RpcError.of("m", "pid is a required argument")) is InvalidArguments


def test_every_code_the_contract_defines_is_classified_on_purpose() -> None:
    contract = json.loads((Path(__file__).parents[3] / "contracts/rpc-contract.json").read_text())
    codes = set(contract["defs"]["RpcErrorCode"]["enum"])

    assert set(_BY_CODE) <= codes
