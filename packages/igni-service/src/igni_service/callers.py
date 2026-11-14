"""Who a request comes from, as a verified token describes them.

A person (`Person`), an app acting as itself (`App`), one end user of an
app (`Space`), or igni itself calling for an organisation (`IgniCall`).
Each caller model reads its fields from a token's `VerifiedClaims`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from igni_service.verified_claims import TokenUse, VerifiedClaims


class CallerKind(StrEnum):
    """Who a request may come from: a person, an app, or an app's space."""

    PERSON = "person"
    """A person, with the token igni issued them for this service (`Person`)."""
    APP = "app"
    """An app acting as itself (`App`)."""
    SPACE = "space"
    """One end user of an app, a producer of its own (`Space`)."""

    @property
    def token_use(self) -> str:
        """The `token_use` claim a token of this kind carries: `user`, `app` or `space`."""
        return TokenUse.USER if self is CallerKind.PERSON else self.value


class Person(BaseModel):
    """A person, as their token describes them, in the one organisation it names."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    user_id: str
    """The person's igni user id (the token's `sub`)."""
    org_id: str
    """The organisation the token is for; every call it makes is in this one."""
    org_name: str = ""
    """The organisation's display name, when the token carries it."""
    org_role: str = "member"
    """`admin` or `member` in `org_id`."""
    email: str = ""
    """The person's email address, when the token carries it."""
    name: str = ""
    """The person's display name, when the token carries it."""
    super_admin: bool = False
    """Whether the person is a super admin of the igni deployment. It does not
    make them an admin of `org_id`."""

    @property
    def kind(self) -> CallerKind:
        """Always `CallerKind.PERSON`: what a `match` on a `Caller` reads."""
        return CallerKind.PERSON

    @property
    def is_org_admin(self) -> bool:
        """Whether the person is an admin of `org_id` (`org_role == "admin"`)."""
        return self.org_role == "admin"

    @property
    def display_name(self) -> str:
        """Their name, or their email address when the token has no name."""
        return self.name or self.email

    @property
    def is_named(self) -> bool:
        """Whether the token named both the person and their organisation."""
        return bool(self.user_id and self.org_id)

    @classmethod
    def from_claims(cls, claims: VerifiedClaims) -> Person:
        """The person a verified token's claims describe (`sub`, `org`, `org_role`, ...).

        Args:
            claims: The verified claims of a token, as ``TokenVerifier.claims``
                read them: the person's ``sub``, ``org``, ``org_name``,
                ``org_role``, ``email``, ``name`` and ``super_admin``.
        """
        return cls(
            user_id=claims.sub,
            org_id=claims.org,
            org_name=claims.org_name,
            org_role=claims.org_role or "member",
            email=claims.email,
            name=claims.name,
            super_admin=claims.super_admin,
        )


class App(BaseModel):
    """An app acting as itself: igni's `app` token for this service."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    app_id: str
    """The app's id, as an org admin registered it (the token's `sub`)."""
    org_id: str
    """The organisation the app belongs to."""
    name: str = ""
    """The app's display name, when the token carries it."""

    @property
    def kind(self) -> CallerKind:
        """Always `CallerKind.APP`."""
        return CallerKind.APP

    @property
    def is_named(self) -> bool:
        """Whether the token named both the app and its organisation."""
        return bool(self.app_id and self.org_id)

    @classmethod
    def from_claims(cls, claims: VerifiedClaims) -> App:
        """The app a verified `app` token's claims describe.

        Args:
            claims: The verified claims of an ``app`` token, as
                ``TokenVerifier.claims`` read them: the app's ``sub``, its
                ``org`` and its ``name``.
        """
        return cls(app_id=claims.sub, org_id=claims.org, name=claims.name)


class Space(BaseModel):
    """One end user of an app, a producer of its own: igni's `space` token for this service."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    space_id: str
    """The space's id at igni (the token's `sub`)."""
    org_id: str
    """The organisation the space's app belongs to."""
    app_id: str
    """The app the space belongs to."""
    external_id: str = ""
    """The app's own name for its end user."""

    @property
    def kind(self) -> CallerKind:
        """Always `CallerKind.SPACE`."""
        return CallerKind.SPACE

    @property
    def is_named(self) -> bool:
        """Whether the token named the space, its app and its organisation."""
        return bool(self.space_id and self.org_id and self.app_id)

    @classmethod
    def from_claims(cls, claims: VerifiedClaims) -> Space:
        """The space a verified `space` token's claims describe.

        Args:
            claims: The verified claims of a ``space`` token, as
                ``TokenVerifier.claims`` read them: the space's ``sub``, its
                ``org``, the app's ``app`` and the app's own name for it,
                ``external_id``.
        """
        return cls(
            space_id=claims.sub,
            org_id=claims.org,
            app_id=claims.app,
            external_id=claims.external_id,
        )


Caller = Person | App | Space
"""Whoever a request comes from, typed: a person, an app or an app's space."""

PEOPLE_ONLY: frozenset[CallerKind] = frozenset({CallerKind.PERSON})
"""What a service accepts unless it says otherwise: people only."""


class IgniCall(BaseModel):
    """igni itself calling this service, for one organisation."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    org_id: str
    """The organisation igni is calling about."""
