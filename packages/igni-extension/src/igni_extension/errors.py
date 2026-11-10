"""What can go wrong, by who has to act on it."""

from __future__ import annotations

from enum import StrEnum


class IgniExtensionError(Exception):
    """Anything this SDK raises on purpose."""


class NotSignedIn(IgniExtensionError):
    """Nobody is signed in to igni, so there is no token for the service.

    The person can fix this: signing in to igni is the answer.
    """

    def __init__(self, message: str = "Sign in to igni to reach this extension's service.") -> None:
        super().__init__(message)


class NotConfigured(IgniExtensionError):
    """igni did not start this process with what the call needs.

    Running outside igni, or an extension that belongs to no service.
    """


class HostUnavailable(IgniExtensionError):
    """The igni host that started this process did not answer as expected."""


class HostErrorCode(StrEnum):
    """Why the igni host refused or failed a request. Each is the string it was."""

    NOT_GRANTED = "not_granted"
    """The manifest's `permissions.host` does not grant the object."""
    NOT_FOUND = "not_found"
    """No such member, or nothing at that id."""
    INVALID = "invalid"
    """The request was malformed: a wrong type, a value out of range."""
    READ_ONLY = "read_only"
    """The property cannot be set."""
    STAGE_2 = "stage_2"
    """Defined in the model, not yet available in this igni."""
    REFUSED = "refused"
    """The person could not have done it either."""
    UNAVAILABLE = "unavailable"
    """What answers it (igni's decision model) could not be started."""
    FAILED = "failed"
    """It was tried and failed."""


class HostError(IgniExtensionError):
    """The igni host refused a request on `ext.host`, or it failed there.

    `code` says which, for code to branch on: `not_granted` (the manifest's
    `permissions.host` lacks the object), `not_found`, `invalid`,
    `read_only`, `stage_2` (defined, not yet available), `refused` (the
    person could not have done it either), `unavailable` (what answers it,
    igni's decision model, could not be started), `failed`. The message is
    a sentence for the extension's author.

    `code` is a `HostErrorCode` — a `StrEnum`, so `code == "not_granted"`
    still holds — or, for a code a newer igni sends that this SDK does not
    know yet, the plain string.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        known = {member.value: member for member in HostErrorCode}
        self.code: str = known.get(code, code)
        """Why, for code to branch on: a `HostErrorCode`, or the plain string for a code this SDK
        does not know.
        """
        self.message = message
        """The host's sentence for the extension's author."""
