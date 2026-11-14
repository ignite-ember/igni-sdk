"""`BearerDependencies`: the FastAPI dependencies that read a request's bearer token.

`IgniService` is built on it, so a route says `Depends(igni.person)`,
`Depends(igni.caller)`, `Depends(igni.igni_call)` and the rest. Outside a
request, `igni.person_of(token)` and `igni.caller_of(token)` check a bare
token and raise instead of answering in HTTP.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Collection
from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from igni_service.errors import IgniUnavailable
from igni_service.tokens import (
    Caller,
    CallerKind,
    IgniCall,
    Person,
    TokenRefused,
    TokenVerifier,
)

logger = logging.getLogger(__name__)

#: Lifts the bearer off a request. `auto_error=False` so a missing header
#: is refused with the same 401 as a bad one.
_BEARER = HTTPBearer(auto_error=False)

#: The body of every refusal. Why is in the RFC 6750 challenge and the
#: log, and only in the terms `TokenRefused` allows: what anybody holding
#: the token could read from it (expired, another audience, the wrong
#: kind), never which signature check failed.
_REFUSAL = "Not authenticated"

_Checked = TypeVar("_Checked")


class BearerDependencies:
    """The dependencies a service's routes take their caller from.

    401 for a missing or refused token; 503 when igni's keys cannot be had
    to check it — nothing is wrong with the token then, and signing in
    again would not help.

    Args:
        verifier: Checks the tokens igni signed for this service.
        accepted_callers: The kinds of caller `caller` lets in.
    """

    def __init__(self, verifier: TokenVerifier, accepted_callers: Collection[CallerKind]) -> None:
        self.verifier = verifier
        """Checks the tokens igni signed for this service; what `person`,
        `caller` and `igni_call` use."""
        self.accepted_callers: frozenset[CallerKind] = frozenset(
            CallerKind(kind) for kind in accepted_callers
        )
        """Who `caller` lets in: people only unless the service says more
        (an app, an app's spaces — igni's service-identity §9.2, §17).
        """

    async def person(
        self, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)]
    ) -> Person:
        """FastAPI dependency: the person a request's token names.

        401 for a missing or refused token; 503 when igni's keys cannot be
        had to check it — nothing is wrong with the token, and signing in
        again would not help.

        Args:
            credentials: The request's bearer credentials: the
                `Authorization` header's scheme and token, or `None` when
                the request sent no bearer token.
        """
        return await self._checked(self.verifier.person, credentials)

    async def caller(
        self, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)]
    ) -> Caller:
        """FastAPI dependency: whoever a request's token names — a `Person`, an
        `App` or a `Space` — among the kinds this service accepts
        (`accepted_callers`, people only by default). 401 for anybody else.

        A bearer route like `person`'s: the extension's page may call it
        (`BearerCors`).

        Args:
            credentials: The request's bearer credentials: the
                `Authorization` header's scheme and token, or `None` when
                the request sent no bearer token.
        """
        return await self._checked(self.caller_of, credentials)

    async def caller_of(self, token: str) -> Caller:
        """`caller` for a bare token, outside an HTTP request (see `person_of`).

        Args:
            token: The caller's bearer token, on its own: a leading
                `Bearer ` is stripped when there is one.
        """
        return await self.verifier.caller(token, accept=self.accepted_callers)

    async def optional_person(
        self, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)]
    ) -> Person | None:
        """FastAPI dependency: the person, or `None` when no token was sent.

        For routes that serve everybody and do more for somebody signed in
        (a public link that also shows the reader's own comments). A token
        that *was* sent and is refused is still a 401: a broken session
        should be noticed, not quietly treated as anonymous.

        Args:
            credentials: The request's bearer credentials: the
                `Authorization` header's scheme and token, or `None` when
                the request sent no bearer token.
        """
        if credentials is None:
            return None
        return await self.person(credentials)

    async def token(
        self, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)]
    ) -> str:
        """FastAPI dependency: the bearer token itself, not yet checked; 401
        when none was sent.

        For a route that checks it later with `person_of` — one that turns
        an unusable token into an anonymous reader instead of a 401, say.
        It is a person's token route all the same: the extension's page may
        call it (`BearerCors`).

        Args:
            credentials: The request's bearer credentials: the
                `Authorization` header's scheme and token, or `None` when
                the request sent no bearer token.
        """
        return self._bare(credentials)

    async def optional_token(
        self, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)]
    ) -> str | None:
        """FastAPI dependency: the bearer token, not yet checked, or `None`.

        Args:
            credentials: The request's bearer credentials: the
                `Authorization` header's scheme and token, or `None` when
                the request sent no bearer token; a scheme other than
                `Bearer` counts as no token.
        """
        if credentials is None or credentials.scheme.lower() != "bearer":
            return None
        return credentials.credentials

    async def person_of(self, token: str) -> Person:
        """The person a bare token names, outside an HTTP request.

        For a WebSocket greeting, a queued job, anything that holds a token
        but no `Authorization` header. Raises `TokenRefused` or
        `IgniUnavailable` rather than an HTTP error, so the caller answers in
        its own protocol.

        Args:
            token: The person's bearer token, on its own: a leading
                `Bearer ` is stripped when there is one.
        """
        return await self.verifier.person(token)

    async def org_admin(
        self, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)]
    ) -> Person:
        """FastAPI dependency: the person, if they are an admin of the organisation
        their token is for (`org_role == "admin"`); 403 for anybody else.

        Being a super admin does not make somebody an organisation's admin.

        Args:
            credentials: The request's bearer credentials: the
                `Authorization` header's scheme and token, or `None` when
                the request sent no bearer token.
        """
        person = await self.person(credentials)
        if not person.is_org_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Organisation admins only"
            )
        return person

    async def igni_call(
        self, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)]
    ) -> IgniCall:
        """FastAPI dependency: igni itself, for the organisation its token names.

        Args:
            credentials: The request's bearer credentials: the
                `Authorization` header's scheme and token, or `None` when
                the request sent no bearer token.
        """
        return await self._checked(self.verifier.igni_call, credentials)

    @staticmethod
    def challenge(refused: TokenRefused | None = None) -> str:
        """The `WWW-Authenticate` value for a 401: bare for no token, RFC 6750's error otherwise.

        Args:
            refused: The refusal to say in the challenge, in words safe to
                show whoever holds the token; `None` when no token was sent,
                and the challenge is bare.
        """
        if refused is None:
            return "Bearer"
        said = " ".join(refused.reason.replace('"', "'").replace("\\", "/").split())
        return f'Bearer error="invalid_token", error_description="{said}"'

    @classmethod
    async def _checked(
        cls,
        check: Callable[[str], Awaitable[_Checked]],
        credentials: HTTPAuthorizationCredentials | None,
    ) -> _Checked:
        """What `check` makes of the request's token, its failures as HTTP errors."""
        token = cls._bare(credentials)
        try:
            return await check(token)
        except TokenRefused as refused:
            raise cls._refused(refused) from None
        except IgniUnavailable as exc:
            raise cls._cannot_check(exc) from exc

    @classmethod
    def _bare(cls, credentials: HTTPAuthorizationCredentials | None) -> str:
        if credentials is None or credentials.scheme.lower() != "bearer":
            # No token at all: RFC 6750 §3.1 — a challenge with no error.
            raise cls._refused()
        return credentials.credentials

    @classmethod
    def _refused(cls, refused: TokenRefused | None = None) -> HTTPException:
        if refused is not None:
            # Visible under uvicorn (`igni_service.logs`): the line the
            # extension's author looks for when their call is a 401.
            logger.info("igni: refused a token: %s", refused.reason)
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_REFUSAL,
            headers={"WWW-Authenticate": cls.challenge(refused)},
        )

    @staticmethod
    def _cannot_check(exc: Exception) -> HTTPException:
        logger.error("igni: cannot check a token: %s", exc)
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="igni server cannot be reached to check this token",
        )
