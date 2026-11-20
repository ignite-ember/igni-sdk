"""Signing a person in to the igni in their Fleet VM: the gateway's `POST /v1/sign-in`.

A Fleet VM keeps a credential of its own, which igni exchanges for the
tokens its model calls use. The gateway hands igni the person's session
for it on their first connection; when igni server later refuses the
credential (revoked, the person signed out), igni says `needs_sign_in`
and the person signs in again here. The gateway wakes the VM, passes igni
the session (the platform's `vm_sign_in`), and answers the credential's
new state. igni-client never does this on its own: the program decides.
"""

from __future__ import annotations

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    ValidatorFunctionWrapHandler,
    field_validator,
)

from igni_client.commands.wire import GatewayRefusal
from igni_client.errors import Unavailable
from igni_client.models import VmCredentialState
from igni_client.targets import Fleet

SIGN_IN_PATH = "/v1/sign-in"


class SignedIn(BaseModel):
    """What the gateway answers a sign-in: the VM it woke and its credential's state."""

    model_config = ConfigDict(extra="allow")

    producer: str = ""
    #: The node the VM runs on, and how it was woken.
    node: str = ""
    how: str = ""
    #: igni's answer to `vm_sign_in`: `ready`, `needs_sign_in` (the session itself was
    #: refused) or `unreachable` (igni server could not be reached), with its message.
    credential: VmCredentialState | None = None

    @field_validator("credential", mode="wrap")
    @classmethod
    def _as_given(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        """A state this version does not know is kept as igni sent it."""
        try:
            return handler(value)
        except ValidationError:
            if not isinstance(value, dict):
                raise
            return VmCredentialState.model_construct(**value)

    @property
    def ready(self) -> bool:
        """Whether igni in the VM now holds a working credential."""
        return self.credential is not None and self.credential.state == "ready"


async def sign_in(fleet: Fleet) -> SignedIn:
    """Sign the person `fleet` connects as in to the igni in their VM.

    Raises `GroupIsLocalOnly` when the person's group runs igni only on the
    desktop (`403 group_local_only`), `NotAllowed` for an app or space
    (only a person signs in) or an inactive producer, `AuthError` for a
    refused session, and `Unavailable` when the gateway is busy, could not
    wake the VM, or cannot be reached.
    """
    response = await fleet.request("POST", SIGN_IN_PATH)
    if response.status_code != 200:
        raise GatewayRefusal.of(response).error()
    try:
        return SignedIn.model_validate_json(response.content)
    except ValidationError as exc:
        raise Unavailable(
            f"the gateway at {fleet.base} answered the sign-in with something else"
        ) from exc


__all__ = ["SIGN_IN_PATH", "SignedIn", "sign_in"]
