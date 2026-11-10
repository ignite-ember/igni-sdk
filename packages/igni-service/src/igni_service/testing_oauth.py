"""igni's token endpoint and revocation endpoint (RFC 6749, RFC 7009), as a service calls them.

Every call authenticates with a client assertion (`ClientAssertionVerifier`).
`client_credentials` issues a service its token for one organisation (or
for none, `scope=revocations`) and an app its own; `authorization_code`
and `refresh_token` issue a person's tokens for a service's own pages.
Revoking a refresh token ends its whole sign-in. `grants` and `revoked`
record what was asked, for a test to read.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

import httpx

from igni_service.testing_assertions import ClientAssertionVerifier
from igni_service.testing_bearers import BearerTokens, TokenHolder
from igni_service.testing_claims import TokenOverrides
from igni_service.testing_clients import ClientKind, FakeClient
from igni_service.testing_sessions import HeldRefresh, SignIns
from igni_service.testing_signer import FakeSigner
from igni_service.testing_wire import OAuthError, RoutedCall, TokenForm
from igni_service.token_endpoint import IssuedTokens


class GrantType(StrEnum):
    CLIENT_CREDENTIALS = "client_credentials"
    AUTHORIZATION_CODE = "authorization_code"
    REFRESH_TOKEN = "refresh_token"  # noqa: S105 — an OAuth grant type, not a token

    @classmethod
    def parse(cls, value: str) -> GrantType | None:
        return next((grant for grant in cls if grant.value == value), None)


Grant = Callable[[FakeClient, TokenForm], httpx.Response]


class FakeTokenEndpoint:
    """`POST /v1/oauth/token` and `POST /v1/oauth/revoke`."""

    def __init__(
        self,
        *,
        verifier: ClientAssertionVerifier,
        bearers: BearerTokens,
        sign_ins: SignIns,
        signer: FakeSigner,
    ) -> None:
        self.verifier = verifier
        self.bearers = bearers
        self.sign_ins = sign_ins
        self.signer = signer
        self.grants: list[str] = []
        """Every grant the token endpoint answered, by `grant_type`."""
        self.revoked: list[str] = []
        """Every refresh token revoked at `/v1/oauth/revoke`, as presented."""

    def reset(self) -> None:
        """Forget what was asked and every sign-in; issued bearer tokens and `jti`s stay."""
        self.grants.clear()
        self.revoked.clear()
        self.sign_ins.reset()

    # ── Routes ──────────────────────────────────────────────────────

    def issue(self, call: RoutedCall) -> httpx.Response:
        form = call.seen.form()
        if not form.is_jwt_bearer:
            return OAuthError(error="invalid_request").to_response()
        proved = self.verifier.verify(form)
        if proved.client is None:
            return proved.to_error()
        self.grants.append(form.grant_type)
        grant = GrantType.parse(form.grant_type)
        if grant is None:
            return OAuthError(error="unsupported_grant_type").to_response()
        return self._grant(grant)(proved.client, form)

    def revoke(self, call: RoutedCall) -> httpx.Response:
        """RFC 7009, as igni answers it: the whole sign-in ends."""
        form = call.seen.form()
        if not form.is_jwt_bearer:
            return OAuthError(error="invalid_client", status=401).to_response()
        proved = self.verifier.verify(form)
        if proved.client is None:
            return proved.to_error()
        if not form.token:
            return OAuthError(error="invalid_request").to_response()
        held = self.sign_ins.held(form.token)
        if held is None:
            if form.token.startswith("eyJ"):  # a JWT: here, only ever an access token
                return OAuthError(error="unsupported_token_type").to_response()
            # Not a token igni would still honour: nothing to revoke.
            return httpx.Response(200)
        if held.client_id != proved.client.client_id:
            return OAuthError(error="invalid_grant").to_response()
        self.revoked.append(form.token)
        self.sign_ins.end(held)
        return httpx.Response(200)

    # ── Grants ──────────────────────────────────────────────────────

    def _grant(self, grant: GrantType) -> Grant:
        grants: dict[GrantType, Grant] = {
            GrantType.CLIENT_CREDENTIALS: self._client_credentials,
            GrantType.AUTHORIZATION_CODE: self._authorization_code,
            GrantType.REFRESH_TOKEN: self._refresh,
        }
        return grants[grant]

    def _client_credentials(self, client: FakeClient, form: TokenForm) -> httpx.Response:
        if client.kind is ClientKind.APP:
            # An app's own token: `organisation` optional, and only its own (§11.1).
            if form.organisation not in ("", client.org_id):
                return OAuthError(error="invalid_target").to_response()
            holder = TokenHolder(client_id=client.client_id, org_id=client.org_id)
            return self._bearer_response(self.bearers.issue_app(holder))
        if form.scope == "revocations" and not form.organisation:
            # A token for no organisation: revocations and served only (§3, §21).
            holder = TokenHolder(client_id=client.client_id)
            return self._bearer_response(self.bearers.issue_service(holder, "revocations"))
        if not form.organisation:
            return OAuthError(error="invalid_request").to_response()
        holder = TokenHolder(client_id=client.client_id, org_id=form.organisation)
        return self._bearer_response(self.bearers.issue_service(holder, "service"))

    def _authorization_code(self, client: FakeClient, form: TokenForm) -> httpx.Response:
        held = self.sign_ins.redeem(form, client.client_id)
        if held is None:
            return OAuthError(error="invalid_grant").to_response()
        return self._user_tokens(client, held)

    def _refresh(self, client: FakeClient, form: TokenForm) -> httpx.Response:
        held = self.sign_ins.renew(form, client.client_id)
        if held is None:
            return OAuthError(error="invalid_grant").to_response()
        return self._user_tokens(client, held)

    def _user_tokens(self, client: FakeClient, held: HeldRefresh) -> httpx.Response:
        """A person's access token for the client's URL, and the next refresh token."""
        refresh = self.sign_ins.hold(held)
        claims = self.signer.directory.claims_for(held.org_id, held.user_id).model_copy(
            update={"azp": client.client_id}
        )
        access = self.signer.sign(held.user_id, claims, TokenOverrides(aud=client.client_uri))
        tokens = IssuedTokens(access_token=access, refresh_token=refresh)
        return httpx.Response(200, json=tokens.model_dump())

    @staticmethod
    def _bearer_response(token: str) -> httpx.Response:
        """A bearer token with no refresh token, which igni then leaves out."""
        tokens = IssuedTokens(access_token=token)
        return httpx.Response(200, json=tokens.model_dump(exclude={"refresh_token"}))


__all__ = ["FakeTokenEndpoint", "GrantType"]
