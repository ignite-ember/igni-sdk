"""An `exp` or `iat` that reads as a number but is not a point in time is refused."""

from __future__ import annotations

import pytest

from igni_service.testing import FakeIgni, ManualClock
from igni_service.tokens import TokenRefused

from .conftest import ORG


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", float("inf"), float("nan")])
@pytest.mark.parametrize("claim", ["exp", "iat"])
async def test_an_exp_or_iat_that_is_not_finite_is_refused(
    fake: FakeIgni, clock: ManualClock, claim: str, bad: object
) -> None:
    now = int(clock.wall())
    payload = {
        "iss": fake.signer.addresses.issuer,
        "sub": "u-ada",
        "aud": fake.signer.addresses.service_url,
        "token_use": "user",
        "org": ORG,
        "iat": now,
        "exp": now + 600,
    } | {claim: bad}
    token = fake.signer.keys.pair.sign_jwt(payload, kid=fake.signer.keys.kid)

    with pytest.raises(TokenRefused, match="exp or iat is not a number"):
        await fake.service().verifier.claims(token, use="user")
