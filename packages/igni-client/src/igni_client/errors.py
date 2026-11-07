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
    """A call igni answered with an error."""

    def __init__(self, method: str, message: str) -> None:
        super().__init__(f"{method}: {message}")
        self.method = method
        self.message = message


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
