"""A `token_use` that is a list or an object is the wrong kind of token, not a crash."""

from __future__ import annotations

import pytest

from igni_service.testing import FakeIgni, ManualClock
from igni_service.tokens import TokenRefused

from .conftest import ORG


@pytest.mark.parametrize("value", [["user"], {"user": 1}, [[]]], ids=["list", "object", "nested"])
async def test_a_token_use_that_is_not_text_is_the_wrong_kind(
    fake: FakeIgni, clock: ManualClock, value: object
) -> None:
    now = int(clock.wall())
    payload = {
        "iss": fake.signer.addresses.issuer,
        "sub": "u-ada",
        "aud": fake.signer.addresses.service_url,
        "token_use": value,
        "org": ORG,
        "iat": now,
        "exp": now + 600,
    }
    token = fake.signer.keys.pair.sign_jwt(payload, kid=fake.signer.keys.kid)

    with pytest.raises(TokenRefused, match="the wrong kind of token"):
        await fake.service().verifier.claims(token, use="user")
