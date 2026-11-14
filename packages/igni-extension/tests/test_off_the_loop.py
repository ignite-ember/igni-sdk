"""`igni_extension.threads.OffTheLoop`: which functions are async, and where each one runs."""

from __future__ import annotations

import functools
import inspect
import threading
from typing import Any

import pytest

from igni_extension.threads import OffTheLoop


async def coroutine(a: int, b: int = 0) -> int:
    return a + b


def plain(a: int, b: int = 0) -> int:
    return a + b


class AsyncCallable:
    async def __call__(self, a: int) -> int:
        return a * 2


class PlainCallable:
    def __call__(self, a: int) -> int:
        return a * 2


class Methods:
    async def a(self) -> int:
        return 1

    def s(self) -> int:
        return 1


@pytest.mark.parametrize(
    ("fn", "expected"),
    [
        (coroutine, True),
        (AsyncCallable(), True),
        (Methods().a, True),
        (plain, False),
        (PlainCallable(), False),
        (Methods().s, False),
        (len, False),
        (lambda: None, False),
        (functools.partial(plain, 1), False),
    ],
)
def test_only_an_async_def_is_async(fn: Any, expected: bool) -> None:
    assert OffTheLoop.is_async(fn) is expected


async def test_an_async_function_runs_on_the_loop_with_its_arguments() -> None:
    assert await OffTheLoop.call(coroutine, 1, b=2) == 3
    assert await OffTheLoop.call(AsyncCallable(), 4) == 8


async def test_a_plain_function_runs_in_a_worker_thread_and_returns_its_result() -> None:
    where: list[threading.Thread] = []

    def work(a: int, b: int = 0) -> int:
        where.append(threading.current_thread())
        return a + b

    assert await OffTheLoop.call(work, 1, b=2) == 3
    assert where != [threading.current_thread()] and len(where) == 1


@pytest.mark.parametrize("raising", ["plain", "async"])
async def test_an_exception_reaches_the_one_who_awaits(raising: str) -> None:
    def fails() -> None:
        raise ValueError("no")

    async def fails_async() -> None:
        raise ValueError("no")

    with pytest.raises(ValueError, match="no"):
        await OffTheLoop.call(fails if raising == "plain" else fails_async)


def test_wrapping_an_async_function_returns_that_function() -> None:
    assert OffTheLoop.wrap(coroutine) is coroutine
    callable_ = AsyncCallable()
    assert OffTheLoop.wrap(callable_) is callable_


async def test_wrapping_a_plain_function_makes_a_coroutine_function_with_its_identity() -> None:
    where: list[threading.Thread] = []

    def work(a: int, b: int = 0) -> int:
        """Adds."""
        where.append(threading.current_thread())
        return a + b

    wrapped = OffTheLoop.wrap(work)

    assert inspect.iscoroutinefunction(wrapped)
    assert (wrapped.__name__, wrapped.__doc__) == ("work", "Adds.")
    assert inspect.signature(wrapped) == inspect.signature(work)
    assert await wrapped(1, b=2) == 3
    assert where != [threading.current_thread()]
