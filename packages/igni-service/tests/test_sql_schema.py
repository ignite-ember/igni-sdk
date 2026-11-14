"""The tables the SDK keeps in a service's database: the published schema a migration depends on."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import DateTime, Float, MetaData, Text, inspect
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from igni_service.tables import IgniTables

SHAPE: dict[str, dict[str, tuple[type, bool]]] = {
    "igni_service_key": {
        "name": (Text, False),
        "kid": (Text, False),
        "private_key_encrypted": (Text, False),
        "created_at": (DateTime, False),
    },
    "igni_web_session": {
        "id_hash": (Text, False),
        "sealed": (Text, False),
        "expires_at": (Float, False),
    },
    "igni_web_login": {
        "state_hash": (Text, False),
        "sealed": (Text, False),
        "expires_at": (Float, False),
    },
}
PRIMARY_KEYS = {
    "igni_service_key": ["name"],
    "igni_web_session": ["id_hash"],
    "igni_web_login": ["state_hash"],
}


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'service.db'}")
    yield engine
    await engine.dispose()


def test_the_metadata_holds_these_three_tables_and_nothing_else() -> None:
    assert isinstance(IgniTables.metadata, MetaData)
    assert set(IgniTables.metadata.tables) == set(SHAPE)
    assert IgniTables.service_key is IgniTables.metadata.tables["igni_service_key"]
    assert IgniTables.web_session is IgniTables.metadata.tables["igni_web_session"]
    assert IgniTables.web_login is IgniTables.metadata.tables["igni_web_login"]


def test_the_metadata_is_the_sdks_own_and_not_a_shared_default() -> None:
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass

    assert IgniTables.metadata is not Base.metadata
    assert IgniTables.metadata.tables.keys().isdisjoint(Base.metadata.tables)


@pytest.mark.parametrize("name", sorted(SHAPE))
def test_each_table_has_its_columns_types_and_nullability(name: str) -> None:
    table = IgniTables.metadata.tables[name]

    assert [c.name for c in table.columns] == list(SHAPE[name])
    for column in table.columns:
        kind, nullable = SHAPE[name][column.name]
        assert isinstance(column.type, kind), column.name
        assert column.nullable is nullable, column.name


def test_the_key_s_created_at_keeps_its_time_zone() -> None:
    column = IgniTables.service_key.c.created_at

    assert isinstance(column.type, DateTime) and column.type.timezone is True


@pytest.mark.parametrize("name", sorted(PRIMARY_KEYS))
def test_each_table_is_keyed_by_one_column(name: str) -> None:
    table = IgniTables.metadata.tables[name]

    assert [c.name for c in table.primary_key.columns] == PRIMARY_KEYS[name]


@pytest.mark.parametrize("name", ["igni_web_session", "igni_web_login"])
def test_expiry_is_indexed_for_the_sweep_on_sessions_and_logins(name: str) -> None:
    table = IgniTables.metadata.tables[name]

    indexed = [[c.name for c in index.columns] for index in table.indexes]
    assert indexed == [["expires_at"]]


def test_the_key_table_has_no_index_beyond_its_key() -> None:
    assert IgniTables.service_key.indexes == set()


async def test_creating_this_metadata_alone_makes_all_three_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(IgniTables.metadata.create_all)

    async with engine.connect() as connection:

        def read(sync: Any) -> tuple[set[str], dict[str, list[str]], dict[str, list[list[str]]]]:
            inspector = inspect(sync)
            names = set(inspector.get_table_names())
            keys = {n: inspector.get_pk_constraint(n)["constrained_columns"] for n in names}
            indexes = {n: [i["column_names"] for i in inspector.get_indexes(n)] for n in names}
            return names, keys, indexes

        names, keys, indexes = await connection.run_sync(read)

    assert names == set(SHAPE)
    assert keys == PRIMARY_KEYS
    assert indexes == {
        "igni_service_key": [],
        "igni_web_session": [["expires_at"]],
        "igni_web_login": [["expires_at"]],
    }


async def test_a_login_in_flight_is_stored_and_found_by_the_hash_of_its_state(
    engine: AsyncEngine,
) -> None:
    from sqlalchemy import delete, insert, select

    login = IgniTables.web_login
    async with engine.begin() as connection:
        await connection.run_sync(IgniTables.metadata.create_all)
        await connection.execute(
            insert(login).values(state_hash="h", sealed="cipher", expires_at=12.5)
        )
        row = (await connection.execute(select(login).where(login.c.state_hash == "h"))).one()
        await connection.execute(delete(login).where(login.c.expires_at < 100))
        left = (await connection.execute(select(login))).all()

    assert tuple(row) == ("h", "cipher", 12.5)
    assert left == []


async def test_a_row_without_its_sealed_part_is_refused_by_the_database(
    engine: AsyncEngine,
) -> None:
    from sqlalchemy import insert
    from sqlalchemy.exc import IntegrityError

    async with engine.begin() as connection:
        await connection.run_sync(IgniTables.metadata.create_all)
    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(
                insert(IgniTables.web_session).values(id_hash="h", expires_at=1.0)
            )
