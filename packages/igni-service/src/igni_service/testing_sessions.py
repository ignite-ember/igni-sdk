"""People signing in to a service: the portal's codes and the refresh tokens behind them.

`SignIns.authorize` plays igni's portal: the browser arrives at
`/authorize`, the person signs in, and the portal sends the browser back
to the service with a code. The code is redeemed once, with its PKCE
verifier, for a refresh token; each refresh replaces it within the same
sign-in, and revoking any of them ends the whole sign-in.
"""

from __future__ import annotations

import hashlib
import uuid
from urllib.parse import parse_qs, urlencode, urlsplit

from pydantic import BaseModel, ConfigDict

from igni_service.clock import Clock
from igni_service.crypto import Base64Url
from igni_service.testing_clients import FakeClientRegistry
from igni_service.testing_directory import FakeDirectory
from igni_service.testing_wire import IgniAddresses, TokenForm

CODE_LIFETIME = 60
"""How long a code the portal hands a browser stays good, in seconds."""


class PortalRefused(ValueError):
    """The portal would not sign anybody in from where the service sent the browser."""


class IssuedCode(BaseModel):
    """An authorization code the portal handed a browser, until it is used."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    client_id: str
    redirect_uri: str
    challenge: str
    user_id: str
    org_id: str
    expires_at: float

    def redeems(self, form: TokenForm, client_id: str, now: float) -> bool:
        """Whether `form`, from `client_id` at `now`, may redeem this code (RFC 7636)."""
        verifier = Base64Url.encode(hashlib.sha256(form.code_verifier.encode()).digest())
        return (
            self.client_id == client_id
            and self.redirect_uri == form.redirect_uri
            and now < self.expires_at
            and verifier == self.challenge
        )


class HeldRefresh(BaseModel):
    """A refresh token igni still honours: whose, for which client and organisation."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    client_id: str
    user_id: str
    org_id: str
    grant: str
    """The sign-in it belongs to: what a revocation ends."""


class AuthorizeRequest(BaseModel):
    """The query a service sends a browser to the portal's `/authorize` with."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    client_id: str = ""
    response_type: str = ""
    code_challenge_method: str = ""
    code_challenge: str = ""
    redirect_uri: str = ""
    state: str = ""

    @classmethod
    def parse(cls, query: str) -> AuthorizeRequest:
        return cls.model_validate({k: v[0] for k, v in parse_qs(query).items()})

    def redirect(self, code: str) -> str:
        """Where the portal sends the browser back: the redirect URI, the code, the state."""
        separator = "&" if "?" in self.redirect_uri else "?"
        return f"{self.redirect_uri}{separator}{urlencode({'code': code, 'state': self.state})}"


class SignIns:
    """The portal's codes and the refresh tokens of every sign-in."""

    def __init__(
        self,
        *,
        addresses: IgniAddresses,
        clock: Clock,
        clients: FakeClientRegistry,
        directory: FakeDirectory,
    ) -> None:
        self.addresses = addresses
        self.clock = clock
        self.clients = clients
        self.directory = directory
        self.codes: dict[str, IssuedCode] = {}
        self.refresh: dict[str, HeldRefresh] = {}

    def authorize(self, location: str, *, user_id: str, org_id: str) -> str:
        """Play the portal: `location` is where the service sent the browser.

        Signs `user_id` in to `org_id` and answers where the portal sends
        the browser back: the client's redirect URI with a code and the
        `state`. Raises `PortalRefused` for anything the portal would refuse.
        """
        parts = urlsplit(location)
        if f"{parts.scheme}://{parts.netloc}{parts.path}" != self.addresses.authorization_endpoint:
            raise PortalRefused(f"{location} is not igni's sign-in page")
        asked = AuthorizeRequest.parse(parts.query)
        client = self.clients.get(asked.client_id)
        if client is None or client.is_revoked:
            raise PortalRefused("unknown client")
        if asked.response_type != "code" or asked.code_challenge_method != "S256":
            raise PortalRefused("only the code flow with S256 is supported")
        if asked.redirect_uri not in client.redirect_uris:
            raise PortalRefused(f"{asked.redirect_uri} is not a registered redirect URI")
        if not asked.code_challenge or not asked.state:
            raise PortalRefused("a challenge and a state are required")
        member = self.directory.member(org_id, user_id)
        if member is None or not member.is_active:
            raise PortalRefused(f"{user_id} is not an active member of {org_id}")
        code = uuid.uuid4().hex
        self.codes[code] = IssuedCode(
            client_id=client.client_id,
            redirect_uri=asked.redirect_uri,
            challenge=asked.code_challenge,
            user_id=member.user_id,
            org_id=org_id,
            expires_at=self.clock.wall() + CODE_LIFETIME,
        )
        return asked.redirect(code)

    def redeem(self, form: TokenForm, client_id: str) -> HeldRefresh | None:
        """A new sign-in for the code `form` redeems, once; `None` if it may not."""
        issued = self.codes.pop(form.code, None)
        if issued is None or not issued.redeems(form, client_id, self.clock.wall()):
            return None
        return HeldRefresh(
            client_id=client_id,
            user_id=issued.user_id,
            org_id=issued.org_id,
            grant=uuid.uuid4().hex,
        )

    def renew(self, form: TokenForm, client_id: str) -> HeldRefresh | None:
        """The sign-in `form`'s refresh token continues, used up; `None` if it may not."""
        held = self.refresh.pop(form.refresh_token, None)
        if held is None or held.client_id != client_id:
            return None
        member = self.directory.member(held.org_id, held.user_id)
        if member is None or not member.is_active:
            return None
        return held

    def hold(self, held: HeldRefresh) -> str:
        """A new refresh token for the sign-in `held` belongs to."""
        token = f"refresh-{uuid.uuid4().hex}"
        self.refresh[token] = held
        return token

    def held(self, token: str) -> HeldRefresh | None:
        return self.refresh.get(token)

    def end(self, held: HeldRefresh) -> None:
        """End the sign-in `held` belongs to: every one of its refresh tokens stops."""
        for token, other in list(self.refresh.items()):
            if other.grant == held.grant:
                del self.refresh[token]

    def reset(self) -> None:
        self.codes.clear()
        self.refresh.clear()


__all__ = ["HeldRefresh", "IssuedCode", "PortalRefused", "SignIns"]
