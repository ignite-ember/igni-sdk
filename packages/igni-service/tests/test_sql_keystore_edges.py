"""SqlKeyStore's edges: a row that vanishes, errors that are not a lost race, and what it exposes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from igni_service import KeyCipher, KeyStoreError, SqlKeyStore, StoredKey
from igni_service.crypto import RsaKeyPair
from igni_service.sql_keystore import THE_KEY
from igni_service.tables import IgniTables


def a_key() -> StoredKey:
    pair = RsaKeyPair.generate()
    return StoredKey(kid=pair.thumbprint(), private_pem=pair.private_pem())


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'service.db'}")
    yield engine
    await engine.dispose()


@pytest.fixture
def cipher() -> KeyCipher:
    return KeyCipher(KeyCipher.generate())


async def test_a_key_written_and_then_not_found_is_said_not_returned_as_none(
    engine: AsyncEngine, cipher: KeyCipher
) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(IgniTables.metadata.create_all)
        await connection.execute(
            text(
                "CREATE TRIGGER forget AFTER INSERT ON igni_service_key "
                "BEGIN DELETE FROM igni_service_key; END"
            )
        )

    with pytest.raises(KeyStoreError, match="written and then not found"):
        await SqlKeyStore(engine, cipher).claim(a_key())


async def test_a_database_error_is_not_taken_for_a_lost_race(
    engine: AsyncEngine, cipher: KeyCipher
) -> None:
    store = SqlKeyStore(engine, cipher, create_table=False)

    with pytest.raises(OperationalError, match="no such table"):
        await store.claim(a_key())
    with pytest.raises(OperationalError, match="no such table"):
        await store.get()


async def test_an_insert_that_fails_for_another_reason_is_raised_though_a_key_is_kept(
    engine: AsyncEngine, cipher: KeyCipher
) -> None:
    await SqlKeyStore(engine, cipher).claim(a_key())

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def fail(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        if statement.lstrip().upper().startswith("INSERT"):
            raise OperationalError(statement, {}, Exception("the disk is full"))

    with pytest.raises(OperationalError, match="disk is full"):
        await SqlKeyStore(engine, cipher).claim(a_key())


async def test_the_row_is_the_one_named_service_and_the_key_is_not_in_clear(
    engine: AsyncEngine, cipher: KeyCipher
) -> None:
    key = a_key()
    await SqlKeyStore(engine, cipher).claim(key)

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text("SELECT name, kid, private_key_encrypted, created_at FROM igni_service_key")
            )
        ).all()

    [row] = rows
    assert (row.name, row.kid) == (THE_KEY, key.kid) == ("service", key.kid)
    assert key.private_pem not in row.private_key_encrypted
    assert row.created_at


async def test_a_second_claim_leaves_the_first_row_as_it_was(
    engine: AsyncEngine, cipher: KeyCipher
) -> None:
    first = a_key()
    store = SqlKeyStore(engine, cipher)
    await store.claim(first)
    async with engine.connect() as connection:
        before = (await connection.execute(text("SELECT * FROM igni_service_key"))).all()

    kept = await store.claim(a_key())

    async with engine.connect() as connection:
        after = (await connection.execute(text("SELECT * FROM igni_service_key"))).all()
    assert kept == first
    assert after == before


async def test_a_table_made_on_first_use_is_there_before_the_first_claim_too(
    engine: AsyncEngine, cipher: KeyCipher
) -> None:
    assert await SqlKeyStore(engine, cipher).get() is None

    async with engine.connect() as connection:
        found = (
            await connection.execute(
                text("SELECT name FROM sqlite_master WHERE name = 'igni_service_key'")
            )
        ).all()
    assert len(found) == 1


def test_the_store_exposes_what_a_service_needs_for_its_migrations(
    engine: AsyncEngine, cipher: KeyCipher
) -> None:
    store = SqlKeyStore(engine, cipher)

    assert store.engine is engine
    assert store.metadata is IgniTables.metadata
    assert store.table is IgniTables.service_key
    assert store.table.name == "igni_service_key"
    assert "igni_service_key" in store.metadata.tables
