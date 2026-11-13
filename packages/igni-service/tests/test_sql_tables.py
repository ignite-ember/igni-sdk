"""TableMaker: tables made once per process, and a lost race between replicas told from a real failure."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from igni_service.sql_tables import TableMaker
from igni_service.tables import IgniTables

TABLES = [IgniTables.service_key]


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'service.db'}")
    yield engine
    await engine.dispose()


def statements(engine: AsyncEngine) -> list[str]:
    """Every statement the engine runs from now on."""
    seen: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        seen.append(statement)

    return seen


async def tables_in(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        return set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))


def creates(seen: list[str]) -> list[str]:
    return [s for s in seen if s.lstrip().upper().startswith("CREATE TABLE")]


async def test_ensure_makes_the_named_tables_and_only_those(engine: AsyncEngine) -> None:
    await TableMaker(engine, TABLES).ensure()

    assert await tables_in(engine) == {"igni_service_key"}


async def test_ensure_is_done_once_and_asks_the_database_nothing_the_second_time(
    engine: AsyncEngine,
) -> None:
    maker = TableMaker(engine, TABLES)
    await maker.ensure()
    seen = statements(engine)

    await maker.ensure()

    assert seen == []


async def test_callers_at_once_in_one_process_make_the_tables_once(engine: AsyncEngine) -> None:
    seen = statements(engine)
    maker = TableMaker(engine, TABLES)

    await asyncio.gather(*(maker.ensure() for _ in range(6)))

    assert len(creates(seen)) == 1


async def test_a_table_that_exists_is_left_alone(engine: AsyncEngine) -> None:
    await TableMaker(engine, TABLES).ensure()
    seen = statements(engine)

    await TableMaker(engine, TABLES).ensure()

    assert creates(seen) == []


async def test_when_the_service_owns_the_tables_none_are_made(engine: AsyncEngine) -> None:
    seen = statements(engine)

    await TableMaker(engine, TABLES, create=False).ensure()

    assert seen == []
    assert await tables_in(engine) == set()


async def test_no_tables_named_makes_none(engine: AsyncEngine) -> None:
    await TableMaker(engine, []).ensure()

    assert await tables_in(engine) == set()


def lose_the_race(engine: AsyncEngine, tmp_path: Path, *, other_replica_makes: bool) -> None:
    """The first CREATE TABLE fails, as it does when another replica's DDL got there first."""
    done = False

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def race(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        nonlocal done
        if done or not statement.lstrip().upper().startswith("CREATE TABLE"):
            return
        done = True
        if other_replica_makes:
            other = create_engine(f"sqlite:///{tmp_path / 'service.db'}")
            IgniTables.metadata.create_all(other, tables=TABLES)
            other.dispose()
        raise OperationalError(statement, {}, Exception("table igni_service_key already exists"))


async def test_a_lost_race_is_fine_when_the_tables_are_there_afterwards(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    lose_the_race(engine, tmp_path, other_replica_makes=True)
    maker = TableMaker(engine, TABLES)

    await maker.ensure()

    assert await tables_in(engine) == {"igni_service_key"}
    seen = statements(engine)
    await maker.ensure()
    assert seen == [], "and it is ready"


async def test_a_failure_that_leaves_a_table_missing_is_raised_and_tried_again_next_time(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    lose_the_race(engine, tmp_path, other_replica_makes=False)
    maker = TableMaker(engine, TABLES)

    with pytest.raises(OperationalError, match="already exists"):
        await maker.ensure()
    assert await tables_in(engine) == set()

    await maker.ensure()

    assert await tables_in(engine) == {"igni_service_key"}
