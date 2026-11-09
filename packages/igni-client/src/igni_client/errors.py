"""What igni-client raises on purpose.

One root, `IgniClientError`, and a type per thing a caller decides
differently about: try again later (`Unavailable`), fix the credential
(`AuthError`), stop (`NotAllowed`), or look at what the agent did
(`RunFailed`, `RunInterrupted`, `ApprovalRequired`).
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


class AuthError(IgniClientError):
    """The credential was refused: an expired or wrong token, or an app key igni does not know."""


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
    error as a sentence; `RpcError.of` reads which kind it is, and each kind
    is a subclass a caller can catch on its own.
    """

    def __init__(self, method: str, message: str) -> None:
        super().__init__(f"{method}: {message}")
        self.method = method
        self.message = message

    @staticmethod
    def of(method: str, message: str) -> RpcError:
        """The kind of error igni's `message` for `method` is."""
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


#: What igni says when it refuses a call for the connection it came on
#: (igni-core's `backend/standing_policy.py` and `message_admission.py`).
_REFUSALS = (
    "only igni's window",
    "a program answers approval requests only with an approver token",
    "only on the platform's control connection",
    "an approver answers once",
)


class RunFailed(IgniClientError):
    """The run ended with an error (`run_error`)."""


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
