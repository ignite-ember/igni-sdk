"""Calling igni's methods: the contract's timeouts and reply kinds, and a call's edges."""

from __future__ import annotations

import asyncio
import gc
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from igni_client import (
    IgniClient,
    InvalidArguments,
    MethodFailed,
    Unavailable,
    UnexpectedAnswer,
    UnknownMethod,
)
from igni_client.api import METHODS
from igni_client.calls import DEFAULT_TIMEOUT, Caller, read, reply_of, spec, timeout_of
from igni_client.models import Command, ErrorMessage, RpcResponse
from igni_client.testing import FakeIgni

_SECONDS = {"instant": 10.0, "io": 30.0, "network": 60.0, "long": 600.0}


def test_a_method_waits_as_long_as_its_duration_class_says() -> None:
    for name, method in METHODS.items():
        if method.duration == "person":
            assert timeout_of(name) is None, name
        else:
            assert timeout_of(name) == _SECONDS[method.duration], name
    assert timeout_of("pick_dir_native") is None


def test_a_method_is_answered_as_its_contract_says() -> None:
    assert reply_of("get_status") == "message"
    assert reply_of("cancel_run") == "rpc_response"
    assert all(reply_of(name) == method.reply for name, method in METHODS.items())


def test_a_method_the_contract_does_not_know_gets_the_defaults() -> None:
    assert timeout_of("brand_new_method") == DEFAULT_TIMEOUT == -1.0
    assert reply_of("brand_new_method") == "rpc_response"
    with pytest.raises(KeyError):
        spec("brand_new_method")
    assert spec("get_status") is METHODS["get_status"]


def test_an_error_message_as_an_answer_is_raised_as_the_kind_it_is() -> None:
    adapter = TypeAdapter(int)

    with pytest.raises(UnknownMethod):
        read("m", ErrorMessage(text="Unknown RPC method: m"), adapter)
    with pytest.raises(MethodFailed, match="m: nope"):
        read("m", ErrorMessage(text="nope"), adapter)
    assert read("m", RpcResponse(result=3), adapter) == 3
    with pytest.raises(UnexpectedAnswer, match="m"):
        read("m", RpcResponse(result=None), adapter)
    with pytest.raises(UnexpectedAnswer):
        read("m", RpcResponse(result="three"), adapter)


async def test_a_message_igni_answers_a_message_with_an_error_raises_its_kind() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.commands = lambda text: ErrorMessage(text="the disk is full")
        with pytest.raises(MethodFailed, match="command: the disk is full"):
            await session.command("/help")


async def test_a_message_of_the_wrong_shape_is_invalid_arguments_naming_its_class() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        caller = Caller(igni._conn)
        with pytest.raises(InvalidArguments, match="Command"):
            await caller.send(Command, {"text": ["not", "text"]})


async def test_the_default_wait_is_the_connection_s_and_none_waits_for_as_long_as_it_takes() -> (
    None
):
    async def slow(args: dict[str, Any]) -> list[Any]:
        await asyncio.sleep(0.2)
        return []

    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        fake.methods.answers["list_background_processes"] = slow
        igni._conn.RPC_TIMEOUT = 0.05
        with pytest.raises(Unavailable, match="got no answer"):
            await igni._conn.ask("list_background_processes")
        with pytest.raises(Unavailable, match="got no answer"):
            await igni._conn.ask("list_background_processes", timeout=DEFAULT_TIMEOUT)
        reply = await igni._conn.ask("list_background_processes", timeout=None)
        assert isinstance(reply, RpcResponse) and reply.result == []


async def test_an_answer_slower_than_nothing_but_inside_the_default_wait_is_still_read() -> None:
    async def slow(args: dict[str, Any]) -> list[Any]:
        await asyncio.sleep(0.2)
        return []

    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        fake.methods.answers["list_background_processes"] = slow
        igni._conn.RPC_TIMEOUT = 5.0
        for given in ({}, {"timeout": DEFAULT_TIMEOUT}):
            reply = await igni._conn.ask("list_background_processes", **given)
            assert isinstance(reply, RpcResponse) and reply.result == []
        with pytest.raises(Unavailable, match="got no answer"):
            await igni._conn.ask("list_background_processes", timeout=0.05)


class _NoArgs(BaseModel):
    pass


async def test_a_method_that_waits_for_a_person_is_not_cut_short() -> None:
    async def chosen(args: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.2)
        return {"path": "/work/x"}

    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        fake.methods.answers["pick_dir_native"] = chosen
        igni._conn.RPC_TIMEOUT = 0.05
        caller = Caller(igni._conn)
        answer = await caller.answer("pick_dir_native", _NoArgs(), TypeAdapter(dict[str, Any]))

    assert answer == {"path": "/work/x"}


async def test_cancelling_one_who_waits_for_a_call_does_not_cancel_the_call() -> None:
    async def slow(args: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.2)
        return {"workflow_run_id": "wf-1", "name": "n"}

    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers["run_workflow"] = slow
        async with session.workflows.run("n") as call:
            waiter = asyncio.ensure_future(call.result())
            await asyncio.sleep(0.05)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            assert (await call.result()).workflow_run_id == "wf-1"


async def test_a_failed_call_nobody_awaits_leaves_no_unretrieved_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers["run_workflow"] = lambda args: RpcResponse(error="the disk is full")
        loop = asyncio.get_running_loop()
        seen: list[dict[str, Any]] = []
        loop.set_exception_handler(lambda _loop, context: seen.append(context))
        try:
            async with session.workflows.run("n"):
                await asyncio.sleep(0.1)
            gc.collect()
        finally:
            loop.set_exception_handler(None)

    assert seen == []


class _Aliased(BaseModel):
    model_config = ConfigDict(validate_by_name=True, serialize_by_alias=True)

    when_to_use: str = Field(default="", alias="whenToUse")


async def test_a_call_s_arguments_go_to_igni_by_their_wire_names() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        fake.methods.answers["list_background_processes"] = []
        await Caller(igni._conn).answer(
            "list_background_processes", _Aliased(when_to_use="now"), TypeAdapter(list[Any])
        )

    [sent] = [c for c in fake.methods.calls if c.method == "list_background_processes"]
    assert sent.args == {"whenToUse": "now"}


async def test_each_call_is_sent_under_an_id_of_its_own_making() -> None:
    async with FakeIgni() as fake, IgniClient(fake.local()) as igni:
        session = await igni.sessions.create()
        fake.methods.answers["run_workflow"] = {"workflow_run_id": "wf-1", "name": "n"}
        first, second = session.workflows.run("n"), session.workflows.run("n")
        await first
        await second

        async with FakeIgni() as other_fake, IgniClient(other_fake.local()) as other:
            other_session = await other.sessions.create()
            other_fake.methods.answers["run_workflow"] = {"workflow_run_id": "wf-2", "name": "n"}
            await other_session.workflows.run("n")

    ids = [c.id for c in fake.methods.calls if c.method == "run_workflow"]
    foreign = [c.id for c in other_fake.methods.calls if c.method == "run_workflow"]
    assert len(set(ids)) == 2 and ids[0] == first._request_id and ids[1] == second._request_id
    assert set(ids).isdisjoint(foreign), "another client's call never carries this client's id"
