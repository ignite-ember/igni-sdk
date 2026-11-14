"""KeyedLocks: one lock per key, dropped once nobody holds or waits on it."""

from __future__ import annotations

import asyncio

import pytest

from igni_service.keyed_locks import KeyedLocks


async def test_a_lock_is_dropped_once_its_holder_is_done() -> None:
    locks = KeyedLocks()

    async with locks.held("org-1"):
        assert len(locks) == 1

    assert len(locks) == 0


async def test_a_lock_is_dropped_when_its_holder_raises() -> None:
    locks = KeyedLocks()

    with pytest.raises(RuntimeError):
        async with locks.held("org-1"):
            raise RuntimeError("igni refused")

    assert len(locks) == 0


async def test_one_key_is_held_by_one_caller_at_a_time_and_kept_while_one_waits() -> None:
    locks = KeyedLocks()
    inside: list[str] = []
    order: list[str] = []

    async def hold(name: str) -> None:
        async with locks.held("org-1"):
            inside.append(name)
            assert len(inside) == 1, "two callers inside one key's lock"
            await asyncio.sleep(0.005)
            assert len(locks) == 1
            order.append(name)
            inside.remove(name)

    await asyncio.gather(hold("a"), hold("b"), hold("c"))

    assert order == ["a", "b", "c"]
    assert len(locks) == 0


async def test_two_keys_do_not_wait_on_each_other() -> None:
    locks = KeyedLocks()
    entered = asyncio.Event()

    async def first() -> None:
        async with locks.held("org-1"):
            await asyncio.wait_for(entered.wait(), timeout=1)

    async def second() -> None:
        async with locks.held("org-2"):
            entered.set()

    await asyncio.gather(first(), second())

    assert len(locks) == 0
