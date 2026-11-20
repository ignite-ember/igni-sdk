"""What igni-client raises on purpose.

One root, `IgniClientError`, and a type per thing a caller decides
differently about: try again later (`Unavailable`), fix the credential
(`AuthError`; `SignInRequired` when a Fleet VM's own one was refused),
stop (`NotAllowed`), or look at what the agent did (`RunFailed`,
`RunInterrupted`, `ApprovalRequired`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from igni_client.events import Requirement


class IgniClientError(Exception):
    """Anything this SDK raises on purpose."""


class Unavailable(IgniClientError):
    """igni could not be reached, went away, or is busy — trying again later may work.

    Raised when the socket cannot open, when the gateway closes it as busy
    (`1013`) more often than the client retries, and when a call gets no
    answer in time.
    """


class RunFailed(IgniClientError):
    """The run ended with an error (`run_error`), or `ask()`'s prompt got an `error` and no run."""


class AuthError(IgniClientError):
    """The credential was refused: an expired or wrong token, or an app key igni does not know."""


class CredentialRefused(AuthError, RunFailed):
    """The igni on a Fleet VM lost its own credential: igni server refused it.

    It is a `RunFailed` too, because the run did fail: code that catches
    `RunFailed` keeps catching it, and code that wants to say how to
    recover catches this first.

    A VM keeps a credential of its own and exchanges it for the tokens its
    model calls use. When igni server refuses it (revoked, reused, the
    person signed out or was removed, the app deleted) igni says so with a
    `vm_credential` push, and every run that needs igni server fails until
    the credential is replaced. `state` is what igni said
    (`needs_sign_in` or `needs_reissue`), `detail` its reason. The client
    does not replace it on its own: the program decides when to sign in.
    """

    def __init__(self, message: str, *, state: str, detail: str = "") -> None:
        super().__init__(message)
        self.state = state
        self.detail = detail

    @staticmethod
    def of(state: str, detail: str = "", *, where: str = "igni") -> CredentialRefused | None:
        """The error a VM credential's `state` means, or `None` for one that works.

        `where` names the igni, and through it the gateway (`Fleet.describe()`).
        """
        reason = f" ({detail})" if detail else ""
        if state == "needs_sign_in":
            return SignInRequired(
                f"{where}: the VM's own credential was refused{reason}; sign the person "
                "in again at the gateway (`POST /v1/sign-in`, which hands igni their "
                "session through the platform's `vm_sign_in`), then ask again",
                state=state,
                detail=detail,
            )
        if state == "needs_reissue":
            return ReissueRequired(
                f"{where}: the app's VM credential was refused{reason}; an organisation "
                "admin re-issues it, and the VM takes it at its next start",
                state=state,
                detail=detail,
            )
        return None


class SignInRequired(CredentialRefused):
    """A person's VM credential was refused: they sign in again at the gateway.

    The gateway's `POST /v1/sign-in` (with the person's bearer token)
    wakes the VM and hands igni the person's session, which igni exchanges
    for a new credential with the platform's `vm_sign_in`; the next run
    then works. igni-client does not sign in by itself.
    """


class ReissueRequired(CredentialRefused):
    """An app's VM credential was refused: an organisation admin re-issues it.

    An app does not sign in. The VM picks the re-issued credential up at
    its next start.
    """


class NotAllowed(IgniClientError):
    """igni answered and said no, and asking again will not change it.

    A producer that is no longer active (removed, deactivated), a lapsed
    licence, or a command in a VM that is not the caller's.
    """


class NotSupported(IgniClientError):
    """The target cannot do this: commands and identity exist only through Fleet's gateway."""


class RpcError(IgniClientError):
    """A call igni answered with an error, or whose answer could not be read.

    `method` is the wire method, `message` what igni said. igni answers an
    error with a sentence and, on a call's reply, a `code` word;
    `RpcError.of` reads which kind it is from the code, and each kind is a
    subclass a caller can catch on its own. A reply with no code is read from
    its sentence instead.
    """

    def __init__(self, method: str, message: str) -> None:
        super().__init__(f"{method}: {message}")
        self.method = method
        self.message = message

    @staticmethod
    def of(method: str, message: str, code: str | None = None) -> RpcError:
        """The kind of error igni's `message` for `method` is.

        `code` is the word igni sent beside the sentence (`forbidden`,
        `unknown_method`, `invalid`, ...), and decides the kind when there is
        one. Without it, as with an `error` message or an igni that sends no
        code, the kind is read from the sentence.
        """
        if code in _BY_CODE:
            return _BY_CODE[code](method, message)
        if code is None:
            return RpcError._of_sentence(method, message)
        return MethodFailed(method, message)

    @staticmethod
    def _of_sentence(method: str, message: str) -> RpcError:
        """The kind of error from igni's words alone, for a reply that has no code."""
        if any(marker in message for marker in _REFUSALS):
            return AccessRefused(method, message)
        if message.startswith("Unknown RPC method"):
            return UnknownMethod(method, message)
        if message.endswith("is a required argument") or message.startswith(f"{method}: '"):
            return InvalidArguments(method, message)
        return MethodFailed(method, message)


class AccessRefused(RpcError, NotAllowed):
    """igni refused the call from this connection: it is igni's window's, or an approver's.

    A program attached with the lockfile's token may run sessions but not
    decide for the person; an approver token (`Local(approver_token=...)`)
    answers approvals, and only igni's own window loosens a rule. Raised
    without asking igni when the connection is known not to reach the
    method (`igni_client.access`).
    """


class UnknownMethod(RpcError):
    """igni does not have the method: it is older than this igni-client."""


class InvalidArguments(RpcError, ValueError):
    """The arguments are not what the method takes — refused before sending, or by igni."""


class UnexpectedAnswer(RpcError):
    """igni's answer is not what the method returns: igni and this igni-client disagree."""


class MethodFailed(RpcError):
    """The method ran and failed; `message` is igni's reason."""


#: The kind of error each `code` igni sends names; every other code is a failure.
_BY_CODE: dict[str, type[RpcError]] = {
    "forbidden": AccessRefused,
    "unknown_method": UnknownMethod,
    "invalid": InvalidArguments,
}

#: What igni says when it refuses a call for the connection it came on
#: (igni-core's `backend/standing_policy.py` and `message_admission.py`).
_REFUSALS = (
    "only igni's window",
    "a program answers approval requests only with an approver token",
    "only on the platform's control connection",
    "an approver answers once",
)


class RunInterrupted(IgniClientError):
    """The connection to igni moved or dropped while the run was going.

    The run may or may not have finished on igni's side; read the
    session's history to find out. Fleet moves a VM between nodes when a
    node drains or fails, and every run in flight then ends with this.
    """


class ApprovalRequired(IgniClientError):
    """`ask()` reached an approval and was given no policy to answer it with.

    The run waits on igni's side for an answer; `requirements` says what it
    asked. Answer it from `Session.send()`, or pass `approve=` to `ask()`.
    """

    def __init__(self, requirements: list[Requirement]) -> None:
        names = ", ".join(r.friendly_name or r.tool_name for r in requirements) or "a tool"
        super().__init__(f"the run is waiting for approval of {names}")
        self.requirements = requirements
