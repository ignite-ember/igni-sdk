"""The generated method table and surface: what the contract says of each, and what is left out.

`test_every_method.py` calls every method with every argument given. This
file covers what that cannot: the table's timing, correlation and
streaming fields against the contract, the docstrings against the
contract's own words, the arguments a caller leaves out, a window change's
token, an answer igni cannot have meant, and an answer that is an error.
"""

from __future__ import annotations

import inspect
import json
import typing
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from igni_client import Call, IgniClient
from igni_client.api import METHODS, IgniApi, SessionApi
from igni_client.errors import MethodFailed, UnexpectedAnswer
from igni_client.testing import FakeIgni, sample

CONTRACT: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "rpc-contract.json").read_text(
        encoding="utf-8"
    )
)


def _method(owner: Any, path: str) -> Any:
    node = owner
    for part in path.split(".")[1:]:
        node = getattr(node, part)
    return node


def _function(spec_python: str, scope: str) -> Any:
    node: Any = IgniApi if scope == "igni" else SessionApi
    parts = spec_python.split(".")[1:]
    for part in parts[:-1]:
        node = typing.get_type_hints(node)[part]
    return getattr(node, parts[-1])


@pytest.mark.parametrize("wire", sorted(METHODS))
def test_a_method_s_timing_and_correlation_are_the_contract_s(wire: str) -> None:
    spec = METHODS[wire]
    contract = CONTRACT["methods"][wire]
    assert spec.duration == contract["duration"]
    assert spec.timeout_seconds == CONTRACT["durations"][contract["duration"]]["timeout_seconds"]
    assert list(spec.may_stream) == contract["may_stream"]
    wanted = contract.get("correlate")
    if wanted is None:
        assert spec.correlate is None
    else:
        assert spec.correlate is not None
        assert (spec.correlate.by, spec.correlate.source, spec.correlate.equals) == (
            wanted["by"],
            wanted.get("from", ""),
            wanted.get("equals", ""),
        )


@pytest.mark.parametrize("wire", sorted(METHODS))
def test_a_method_s_docstring_opens_with_the_contract_s_words(wire: str) -> None:
    if wire == "attach_session":
        pytest.skip("igni.sessions.attach is hand-extended: it also returns the session")
    spec = METHODS[wire]
    doc = inspect.getdoc(_function(spec.python, spec.scope)) or ""
    assert doc.startswith(CONTRACT["methods"][wire]["doc"].strip()), wire


@pytest.mark.parametrize("wire", sorted(METHODS))
def test_a_method_with_a_followed_call_says_how_to_follow_it(wire: str) -> None:
    if wire == "attach_session":
        pytest.skip("igni.sessions.attach is hand-extended: checked through the client")
    spec = METHODS[wire]
    function = _function(spec.python, spec.scope)
    doc = inspect.getdoc(function) or ""
    returns = typing.get_type_hints(function)["return"]
    assert (typing.get_origin(returns) is Call) == spec.followed
    assert ("async with" in doc) == spec.followed


async def test_the_arguments_left_out_are_sent_as_their_defaults() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        for attempt in (
            igni.files.list_dirs(),
            igni.processes.tail(1),
            session.files.complete(),
            session.history.search("q"),
            session.scheduler.list(),
            igni.auth.set_server("https://a.example"),
            igni.agents.cancel_run(),
        ):
            with pytest.raises(MethodFailed):  # the fake has no answer: only what went out counts
                await attempt
    sent = {c.method: dict(c.args) for c in fake.methods.calls}

    assert sent["list_dirs"] == {"path": None, "show_hidden": False}
    assert sent["read_process_tail"] == {"pid": 1, "tail": 200}
    assert sent["complete_files"] == {"limit": 50, "query": ""}
    assert sent["search_chat"]["limit"] == 50
    assert sent["get_scheduled_tasks"] == {"include_done": True}
    assert sent["set_server"] == {"api_url": "https://a.example", "portal_url": ""}
    assert sent["cancel_agent_run"] == {"run_id": ""}


async def test_a_session_list_that_leaves_done_tasks_out_says_so() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers["get_scheduled_tasks"] = []
        await session.scheduler.list(include_done=False)
    [call] = [c for c in fake.methods.calls if c.method == "get_scheduled_tasks"]
    assert call.args == {"include_done": False}


async def test_a_limit_of_zero_or_below_goes_to_igni_unchanged() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers["search_chat"] = []
        await session.history.search("é\u202e" + "x" * 100_000, limit=-1)
        with pytest.raises(MethodFailed):  # the fake has no answer: only what went out counts
            await session.files.complete(limit=0)
    sent = {c.method: c.args for c in fake.methods.calls}
    assert sent["search_chat"]["limit"] == -1
    assert sent["search_chat"]["query"] == "é\u202e" + "x" * 100_000
    assert sent["complete_files"]["limit"] == 0


async def test_a_window_change_without_a_token_gets_its_own_and_one_given_is_kept() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        fake.methods.answers["window_model"] = {"op": "write", "rev": 1}
        for kwargs in (
            {"token": ""},
            {"token": ""},
            {"token": "mine"},
        ):
            await igni.window.model(op="write", window="w", field="f", value=1, **kwargs)
    tokens = [c.args["token"] for c in fake.methods.calls if c.method == "window_model"]
    assert tokens[2] == "mine"
    assert tokens[0] and tokens[1] and tokens[0] != tokens[1]
    assert "mine" not in tokens[:2]


PLAYED = {
    "attach_session",
    "get_session_id",
    "list_sessions",
    "get_model_registry",
    "switch_model",
    "get_status",
    "get_chat_history",
    "cancel_run",
}


async def _call(igni: IgniClient, session: Any, spec: Any) -> Any:
    owner: Any = igni if spec.python.startswith("igni.") else session
    method = _method(owner, spec.python)
    hints = typing.get_type_hints(method)
    arguments = {n: sample(hints[n]) for n in inspect.signature(method).parameters if n != "self"}
    return await method(**arguments)


@pytest.mark.parametrize(
    "wire", sorted(w for w in METHODS if w not in PLAYED and METHODS[w].reply == "rpc_response")
)
async def test_a_method_igni_answers_with_an_error_raises_instead_of_returning(wire: str) -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        with pytest.raises(MethodFailed, match="no answer"):
            await _call(igni, session, METHODS[wire])


@pytest.mark.parametrize(
    "wire", sorted(w for w in METHODS if w not in PLAYED and METHODS[w].reply == "rpc_response")
)
async def test_an_answer_that_does_not_fit_the_result_is_refused(wire: str) -> None:
    spec = METHODS[wire]
    function = _function(spec.python, spec.scope)
    returns = typing.get_type_hints(function)["return"]
    result_type = typing.get_args(returns)[0] if typing.get_origin(returns) is Call else returns
    adapter = TypeAdapter(result_type)
    unfit = [c for c in (None, "no", 7, [7], {"unrelated": 1}, []) if _refused(adapter, c)]
    if not unfit:
        pytest.skip("every answer fits this result")
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers[wire] = unfit[0]
        with pytest.raises(UnexpectedAnswer, match=wire):
            await _call(igni, session, spec)


def _refused(adapter: TypeAdapter[Any], value: Any) -> bool:
    try:
        adapter.validate_python(value)
    except ValidationError:
        return True
    return False


async def test_a_result_that_may_be_null_is_returned_as_none() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers.update(
            {"check_for_update": None, "get_cloud_plan": None, "pop_pending_loop_iteration": None}
        )
        assert await igni.check_for_update() is None
        assert await session.auth.plan() is None
        assert await session.loop.next_iteration() is None
