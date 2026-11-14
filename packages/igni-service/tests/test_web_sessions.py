"""The web session stores: what both keep, forget, expire and hand out once."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from igni_service import KeyCipher, KeyStoreError, Person, SqlWebSessionStore
from igni_service.tables import IgniTables
from igni_service.testing import ManualClock
from igni_service.web_sessions import (
    Digest,
    LoginAttempt,
    MemoryWebSessionStore,
    WebSession,
    WebSessionStore,
)

from .conftest import ORG


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'web.db'}")
    yield engine
    await engine.dispose()


@pytest.fixture(params=["memory", "sql"])
def store(request: pytest.FixtureRequest, clock: ManualClock) -> WebSessionStore:
    if request.param == "memory":
        return MemoryWebSessionStore(clock=clock)
    engine: AsyncEngine = request.getfixturevalue("engine")
    return SqlWebSessionStore(engine, KeyCipher(KeyCipher.generate()), clock=clock)


def session_for(
    clock: ManualClock, *, refresh: str = "refresh-1", lives: float = 3600
) -> WebSession:
    return WebSession(
        person=Person(user_id="u-max", org_id=ORG),
        access_token="eyJ-access",
        refresh_token=refresh,
        access_expires_at=clock.wall() + 600,
        expires_at=clock.wall() + lives,
    )


def attempt_for(clock: ManualClock, state: str = "s1", lives: float = 600) -> LoginAttempt:
    return LoginAttempt(
        state=state, verifier="v-" + state, return_to="/x", expires_at=clock.wall() + lives
    )


# ── Both stores ──────────────────────────────────────────────────────


def test_both_stores_are_web_session_stores(engine: AsyncEngine, clock: ManualClock) -> None:
    assert isinstance(MemoryWebSessionStore(), WebSessionStore)
    assert isinstance(SqlWebSessionStore(engine, KeyCipher(KeyCipher.generate())), WebSessionStore)
    assert not isinstance(object(), WebSessionStore)


async def test_a_session_nobody_put_is_none(store: WebSessionStore) -> None:
    assert await store.get("never-put") is None


async def test_a_session_is_kept_replaced_and_forgotten(
    store: WebSessionStore, clock: ManualClock
) -> None:
    first = session_for(clock)
    renewed = session_for(clock, refresh="refresh-2")

    await store.put("id", first)
    assert await store.get("id") == first
    await store.put("id", renewed)
    assert await store.get("id") == renewed
    await store.delete("id")
    assert await store.get("id") is None


async def test_deleting_one_session_leaves_the_others(
    store: WebSessionStore, clock: ManualClock
) -> None:
    await store.put("a", session_for(clock, refresh="ra"))
    await store.put("b", session_for(clock, refresh="rb"))

    await store.delete("a")

    assert await store.get("a") is None
    held = await store.get("b")
    assert held is not None and held.refresh_token == "rb"


async def test_forgetting_a_session_nobody_holds_is_not_an_error(store: WebSessionStore) -> None:
    await store.delete("never-put")
    await store.delete("")


@pytest.mark.parametrize("session_id", ["", "café", "日本", "a b/c?d", "x" * 5000])
async def test_any_text_is_a_session_id(
    store: WebSessionStore, clock: ManualClock, session_id: str
) -> None:
    held = session_for(clock)

    await store.put(session_id, held)

    assert await store.get(session_id) == held
    assert await store.get(session_id + "x") is None


async def test_a_session_is_dead_at_exactly_its_expiry_not_before(
    store: WebSessionStore, clock: ManualClock
) -> None:
    await store.put("id", session_for(clock, lives=100))

    clock.advance(99)
    assert await store.get("id") is not None
    clock.advance(1)
    assert await store.get("id") is None


async def test_a_login_is_taken_once(store: WebSessionStore, clock: ManualClock) -> None:
    attempt = attempt_for(clock)
    await store.put_login(attempt)

    assert await store.take_login("s1") == attempt
    assert await store.take_login("s1") is None


async def test_a_login_nobody_started_is_none(store: WebSessionStore) -> None:
    assert await store.take_login("never-started") is None


async def test_each_login_is_taken_by_its_own_state(
    store: WebSessionStore, clock: ManualClock
) -> None:
    await store.put_login(attempt_for(clock, "one"))
    await store.put_login(attempt_for(clock, "two"))

    taken = await store.take_login("two")
    assert taken is not None and taken.verifier == "v-two"
    other = await store.take_login("one")
    assert other is not None and other.verifier == "v-one"


async def test_a_login_is_void_at_exactly_its_expiry_and_taking_it_then_gives_nothing(
    store: WebSessionStore, clock: ManualClock
) -> None:
    await store.put_login(attempt_for(clock, "early", lives=100))
    await store.put_login(attempt_for(clock, "late", lives=100))

    clock.advance(99)
    assert await store.take_login("early") is not None
    clock.advance(1)
    assert await store.take_login("late") is None
    assert await store.take_login("late") is None


async def test_two_takes_at_once_give_the_attempt_to_exactly_one(
    store: WebSessionStore, clock: ManualClock
) -> None:
    await store.put_login(attempt_for(clock))

    taken = await asyncio.gather(*(store.take_login("s1") for _ in range(8)))

    assert len([t for t in taken if t is not None]) == 1


# ── The SQL store ────────────────────────────────────────────────────


async def _count(engine: AsyncEngine, table: object) -> int:
    async with engine.connect() as connection:
        return int(
            (await connection.execute(select(func.count()).select_from(table))).scalar_one()  # type: ignore[arg-type]
        )


async def test_the_sql_store_keeps_no_cookie_state_or_token_in_clear(
    engine: AsyncEngine, clock: ManualClock
) -> None:
    store = SqlWebSessionStore(engine, KeyCipher(KeyCipher.generate()), clock=clock)
    await store.put("cookie-secret", session_for(clock, refresh="refresh-secret"))
    await store.put_login(attempt_for(clock, "state-secret"))

    async with engine.connect() as connection:
        sessions = (await connection.execute(select(IgniTables.web_session))).all()
        logins = (await connection.execute(select(IgniTables.web_login))).all()

    [held] = sessions
    [login] = logins
    assert held.id_hash == hashlib.sha256(b"cookie-secret").hexdigest()
    assert login.state_hash == hashlib.sha256(b"state-secret").hexdigest()
    for text in (str(tuple(held)), str(tuple(login))):
        assert "refresh-secret" not in text and "eyJ-access" not in text
        assert "v-state-secret" not in text and "cookie-secret" not in text
    assert held.expires_at == clock.wall() + 3600
    assert login.expires_at == clock.wall() + 600


async def test_a_login_starting_deletes_the_sign_ins_and_sessions_that_have_expired(
    engine: AsyncEngine, clock: ManualClock
) -> None:
    store = SqlWebSessionStore(engine, KeyCipher(KeyCipher.generate()), clock=clock)
    await store.put("dead", session_for(clock, lives=100))
    await store.put("alive", session_for(clock, lives=1000))
    await store.put_login(attempt_for(clock, "dead", lives=100))
    await store.put_login(attempt_for(clock, "alive", lives=1000))
    assert await _count(engine, IgniTables.web_session) == 2
    assert await _count(engine, IgniTables.web_login) == 2

    clock.advance(100)
    await store.put_login(attempt_for(clock, "new"))

    assert await _count(engine, IgniTables.web_session) == 1
    assert await _count(engine, IgniTables.web_login) == 2
    assert await store.get("alive") is not None
    assert await store.take_login("alive") is not None
    assert await store.take_login("new") is not None


async def test_the_sql_store_does_not_prune_when_only_a_session_is_put(
    engine: AsyncEngine, clock: ManualClock
) -> None:
    store = SqlWebSessionStore(engine, KeyCipher(KeyCipher.generate()), clock=clock)
    await store.put("dead", session_for(clock, lives=100))
    clock.advance(200)

    await store.put("other", session_for(clock))

    assert await _count(engine, IgniTables.web_session) == 2


async def test_a_row_sealed_under_another_key_is_refused_in_the_key_s_own_words(
    engine: AsyncEngine, clock: ManualClock
) -> None:
    await SqlWebSessionStore(engine, KeyCipher(KeyCipher.generate()), clock=clock).put(
        "id", session_for(clock)
    )
    await SqlWebSessionStore(engine, KeyCipher(KeyCipher.generate()), clock=clock).put_login(
        attempt_for(clock)
    )
    other = SqlWebSessionStore(engine, KeyCipher(KeyCipher.generate()), clock=clock)

    with pytest.raises(KeyStoreError):
        await other.get("id")
    with pytest.raises(KeyStoreError):
        await other.take_login("s1")


async def test_a_store_told_not_to_create_its_tables_does_not(
    engine: AsyncEngine, clock: ManualClock
) -> None:
    store = SqlWebSessionStore(
        engine, KeyCipher(KeyCipher.generate()), create_table=False, clock=clock
    )

    with pytest.raises(SQLAlchemyError):
        await store.get("id")
    with pytest.raises(SQLAlchemyError):
        await store.put_login(attempt_for(clock))


async def test_a_store_creates_its_tables_on_first_use_by_default(
    engine: AsyncEngine, clock: ManualClock
) -> None:
    store = SqlWebSessionStore(engine, KeyCipher(KeyCipher.generate()), clock=clock)

    assert await store.get("id") is None
    assert await store.take_login("s1") is None
    assert await _count(engine, IgniTables.web_session) == 0
    assert await _count(engine, IgniTables.web_login) == 0


async def test_a_second_sql_store_on_the_same_database_sees_the_first_one_s_sessions(
    engine: AsyncEngine, clock: ManualClock
) -> None:
    cipher = KeyCipher(KeyCipher.generate())
    one = SqlWebSessionStore(engine, cipher, clock=clock)
    two = SqlWebSessionStore(engine, cipher, clock=clock)
    held = session_for(clock)

    await one.put("id", held)
    await one.put_login(attempt_for(clock))

    assert await two.get("id") == held
    assert await two.take_login("s1") is not None
    assert await one.take_login("s1") is None


# ── The memory store ─────────────────────────────────────────────────


async def test_the_memory_store_holds_only_digests_of_what_it_is_given(
    clock: ManualClock,
) -> None:
    store = MemoryWebSessionStore(clock=clock)
    await store.put("cookie-secret", session_for(clock))
    await store.put_login(attempt_for(clock, "state-secret"))

    keys = [*store._sessions, *store._logins]

    assert sorted(keys) == sorted([Digest.of("cookie-secret"), Digest.of("state-secret")])


async def test_the_memory_store_drops_a_session_it_finds_expired(clock: ManualClock) -> None:
    store = MemoryWebSessionStore(clock=clock)
    await store.put("id", session_for(clock, lives=10))
    clock.advance(10)

    assert await store.get("id") is None
    assert store._sessions == {}


async def test_the_memory_store_reads_the_system_clock_when_given_none() -> None:
    store = MemoryWebSessionStore()
    live = LoginAttempt(state="s", verifier="v", return_to="/", expires_at=1e12)
    dead = LoginAttempt(state="d", verifier="v", return_to="/", expires_at=1.0)
    await store.put_login(live)
    await store.put_login(dead)

    assert await store.take_login("s") == live
    assert await store.take_login("d") is None


# ── Digest and the models ────────────────────────────────────────────


def test_a_digest_is_the_hex_sha256_of_the_text() -> None:
    assert Digest.of("abc") == ("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    assert Digest.of("") == hashlib.sha256(b"").hexdigest()
    assert Digest.of("café") == hashlib.sha256("café".encode()).hexdigest()


def test_a_session_and_an_attempt_cannot_be_changed(clock: ManualClock) -> None:
    held = session_for(clock)
    attempt = attempt_for(clock)

    with pytest.raises(ValidationError):
        held.refresh_token = "other"
    with pytest.raises(ValidationError):
        attempt.return_to = "/other"


def test_a_session_and_an_attempt_need_all_their_fields() -> None:
    with pytest.raises(ValidationError):
        WebSession.model_validate({"access_token": "a"})
    with pytest.raises(ValidationError):
        LoginAttempt.model_validate({"state": "s", "verifier": "v"})
    with pytest.raises(ValidationError):
        LoginAttempt.model_validate(
            {"state": "s", "verifier": "v", "return_to": "/", "expires_at": "soon"}
        )


# ── What the Args sections say ───────────────────────────────────────


def documented_arguments(doc: str) -> list[str]:
    """The names an ``Args:`` section documents, in order."""
    names: list[str] = []
    lines = doc.split("\n")
    for index, line in enumerate(lines):
        if line.strip() != "Args:":
            continue
        base = len(line) - len(line.lstrip())
        item = None
        for body in lines[index + 1 :]:
            if body.strip() and len(body) - len(body.lstrip()) <= base:
                break
            indent = len(body) - len(body.lstrip())
            if body.strip() and (item is None or indent == item):
                item = indent
                names.append(body.strip().split(":", 1)[0])
    return names


DOCUMENTED_CALLABLES = [
    (f"{owner.__name__}.{name}", member)
    for owner in (WebSessionStore, MemoryWebSessionStore, SqlWebSessionStore)
    for name, member in vars(owner).items()
    if inspect.isfunction(member) and not name.startswith("_")
] + [
    ("Digest.of", vars(Digest)["of"].__func__),
    ("WebSessionStore", WebSessionStore),
    ("MemoryWebSessionStore", MemoryWebSessionStore),
    ("SqlWebSessionStore", SqlWebSessionStore),
]


def test_the_session_stores_are_documented_through_the_inventory() -> None:
    """The inventory holds the five methods of each store, the digest and the three classes."""
    names = {name for name, _ in DOCUMENTED_CALLABLES}
    for owner in ("WebSessionStore", "MemoryWebSessionStore", "SqlWebSessionStore"):
        for method in ("get", "put", "delete", "put_login", "take_login"):
            assert f"{owner}.{method}" in names
    assert "Digest.of" in names


@pytest.mark.parametrize(
    "name,member", DOCUMENTED_CALLABLES, ids=[n for n, _ in DOCUMENTED_CALLABLES]
)
def test_each_args_section_names_exactly_the_parameters_the_callable_takes(
    name: str, member: object
) -> None:
    doc = inspect.getdoc(member) or ""
    taken = [p for p in inspect.signature(member).parameters if p not in ("self", "cls")]  # type: ignore[arg-type]
    assert documented_arguments(doc) == taken, name
