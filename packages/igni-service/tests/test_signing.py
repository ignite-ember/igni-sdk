"""SigningKey: one key per deployment, its client assertions, and the bundle and asset signatures."""

from __future__ import annotations

import asyncio
import logging

import jwt
import pytest

from igni_service import KeyStoreError, MemoryKeyStore, StoredKey
from igni_service.crypto import AssetClaim, BundleClaim
from igni_service.signing import SigningKey
from igni_service.testing import ManualClock

GENERATED = "igni: generated a new key pair for this deployment"


class FlakyStore:
    """A key store whose reads fail until told to heal."""

    def __init__(self) -> None:
        self.inner = MemoryKeyStore()
        self.broken = True
        self.reads = 0

    async def get(self) -> StoredKey | None:
        self.reads += 1
        if self.broken:
            raise KeyStoreError("the database is away")
        return await self.inner.get()

    async def claim(self, key: StoredKey) -> StoredKey:
        return await self.inner.claim(key)


class SlowStore(MemoryKeyStore):
    """A store where every replica reads before any has claimed."""

    def __init__(self, shared: MemoryKeyStore, gate: asyncio.Barrier) -> None:
        super().__init__()
        self.shared = shared
        self.gate = gate

    async def get(self) -> StoredKey | None:
        found = await self.shared.get()
        await self.gate.wait()
        return found

    async def claim(self, key: StoredKey) -> StoredKey:
        return await self.shared.claim(key)


async def test_the_first_start_makes_a_key_keeps_it_and_says_so_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = MemoryKeyStore()
    signing = SigningKey(store)

    with caplog.at_level(logging.WARNING, logger="igni_service.signing"):
        pair = await signing.pair()
        again = await signing.pair()

    assert pair is again
    kept = await store.get()
    assert kept is not None
    assert kept.kid == pair.thumbprint() == await signing.thumbprint()
    assert [r.getMessage() for r in caplog.records] == [GENERATED]


async def test_a_key_already_kept_is_used_and_nothing_is_generated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = MemoryKeyStore()
    first = await SigningKey(store).pair()
    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="igni_service.signing"):
        second = await SigningKey(store).pair()

    assert second.thumbprint() == first.thumbprint()
    assert caplog.records == []


async def test_a_replica_that_lost_the_race_uses_the_winners_key_and_does_not_say_it_made_one(
    caplog: pytest.LogCaptureFixture,
) -> None:
    shared = MemoryKeyStore()
    gate = asyncio.Barrier(3)
    replicas = [SigningKey(SlowStore(shared, gate)) for _ in range(3)]

    with caplog.at_level(logging.WARNING, logger="igni_service.signing"):
        pairs = await asyncio.gather(*(r.pair() for r in replicas))

    assert len({p.thumbprint() for p in pairs}) == 1
    kept = await shared.get()
    assert kept is not None
    assert pairs[0].thumbprint() == kept.kid
    assert [r.getMessage() for r in caplog.records] == [GENERATED], "only the winner says so"


async def test_a_store_that_fails_is_not_remembered_as_having_no_key() -> None:
    store = FlakyStore()
    signing = SigningKey(store)

    with pytest.raises(KeyStoreError, match="away"):
        await signing.pair()
    store.broken = False
    pair = await signing.pair()

    assert pair.thumbprint() == (await store.inner.get()).kid  # type: ignore[union-attr]


async def test_a_client_assertion_names_the_client_the_audience_and_a_minute() -> None:
    clock = ManualClock()
    signing = SigningKey(MemoryKeyStore(), clock=clock)
    pair = await signing.pair()

    assertion = await signing.assertion(client_id="client-1", audience="https://igni.test")

    claims = jwt.decode(
        assertion,
        pair.public_jwk().public_key(),
        algorithms=["RS256"],
        audience="https://igni.test",
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims["iss"] == claims["sub"] == "client-1"
    assert claims["iat"] == int(clock.wall())
    assert claims["exp"] == int(clock.wall()) + 60 == claims["iat"] + SigningKey.ASSERTION_LIFETIME
    assert jwt.get_unverified_header(assertion) == {
        "alg": "RS256",
        "kid": pair.thumbprint(),
        "typ": "JWT",
    }
    assert SigningKey.ASSERTION_LIFETIME <= 300, "igni takes no assertion that lives longer"


async def test_an_assertion_follows_the_clock_and_is_never_used_twice() -> None:
    clock = ManualClock()
    signing = SigningKey(MemoryKeyStore(), clock=clock)

    first = await signing.assertion(client_id="c", audience="a")
    clock.advance(1000)
    second = await signing.assertion(client_id="c", audience="a")

    one = jwt.decode(first, options={"verify_signature": False})
    two = jwt.decode(second, options={"verify_signature": False})
    assert two["iat"] - one["iat"] == 1000
    assert one["jti"] != two["jti"]


async def test_the_bundle_and_an_asset_are_signed_over_their_claims_with_the_service_key() -> None:
    signing = SigningKey(MemoryKeyStore())
    pair = await signing.pair()
    bundle = BundleClaim(extension="ext", version="1.0.0", sha256="ab" * 32)
    asset = AssetClaim(asset="cd" * 32, size=12)

    signed_bundle = await signing.sign_bundle(bundle)
    signed_asset = await signing.sign_asset(asset)

    assert signed_bundle == pair.sign_bundle(bundle)
    assert signed_asset == pair.sign_asset(asset)
    assert signed_bundle != signed_asset
    for signed, claim in ((signed_bundle, bundle), (signed_asset, asset)):
        header = jwt.get_unverified_header(signed)
        assert header["kid"] == pair.thumbprint()
        payload = jwt.api_jws.PyJWS().decode(
            signed, pair.public_jwk().public_key(), algorithms=["RS256"]
        )
        assert payload == claim.model_dump_json().encode()


async def test_the_store_is_the_one_it_was_given() -> None:
    store = MemoryKeyStore()

    assert SigningKey(store).store is store


async def test_callers_of_one_process_asking_at_once_make_and_claim_one_key() -> None:
    class Counting(MemoryKeyStore):
        claims = 0

        async def get(self) -> StoredKey | None:
            await asyncio.sleep(0.01)
            return await super().get()

        async def claim(self, key: StoredKey) -> StoredKey:
            Counting.claims += 1
            return await super().claim(key)

    signing = SigningKey(Counting())

    pairs = await asyncio.gather(*(signing.pair() for _ in range(5)))

    assert Counting.claims == 1
    assert all(pair is pairs[0] for pair in pairs)
