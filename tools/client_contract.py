"""igni-core's RPC contract, as igni-client's generator reads it.

igni-core publishes ``docs/rpc-contract.json`` (``igni_core.protocol.rpc_contract``):
every RPC method — its arguments, its result, who may call it, what it acts
on, what it streams and how a client tells which of the messages igni
streams are its own — and every message on igni's socket, each as JSON
Schema over one shared ``defs`` table. This repository keeps a copy in
``contracts/rpc-contract.json`` (``make contracts``) and generates
igni-client's models and methods from it (``tools/client_codegen.py``).

The models here read the file whole: a key igni-core adds that they do not
know fails the read, so the generator never silently ignores part of the
contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

#: The copy this repository builds against.
CONTRACT_FILE = Path(__file__).resolve().parent.parent / "contracts" / "rpc-contract.json"

Scope = Literal["session", "igni"]
Access = Literal["client", "approver", "window", "page", "platform"]
Direction = Literal["to_client", "to_igni", "both"]

#: The prefix a stream name carries when it is a push notification's channel.
PUSH_PREFIX = "push_notification:"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DurationContract(_Strict):
    """One class of how long a call takes."""

    #: What takes that long.
    doc: str
    #: A timeout that leaves a healthy call room; ``None``: no timeout.
    timeout_seconds: int | None = None


class Correlation(_Strict):
    """How a client tells which of the messages igni streams are a call's own.

    ``by`` is the place in a streamed message that holds the value found
    at ``from`` — a place in the call — or at ``equals``, a fixed value.
    """

    #: Where in the streamed message the value is: ``id``, ``session_id``,
    #: ``run_id``, ``payload.<field>`` or ``channel``.
    by: str
    #: Where in the call the value comes from: ``request.id``,
    #: ``request.session_id``, ``args.<field>`` or ``result.<field>``.
    source: str = Field(default="", alias="from")
    #: A fixed value the message must carry.
    equals: str = ""


class MethodContract(_Strict):
    """One RPC method."""

    area: str
    summary: str
    doc: str
    scope: Scope
    access: Access
    args: dict[str, Any]
    result: dict[str, Any]
    streams: list[str] = Field(default_factory=list)
    reply: Literal["rpc_response", "message"] = "rpc_response"
    #: The push channels the call may cause while it runs, beyond the
    #: messages it streams itself.
    may_stream: list[str] = Field(default_factory=list)
    #: How a client tells which of the messages igni streams are this
    #: call's; ``None`` where there is nothing to tell them apart by.
    correlate: Correlation | None = None
    #: How long the call takes: ``instant``, ``io``, ``network``,
    #: ``long`` or ``person``.
    duration: str = ""
    #: A timeout that leaves a healthy call room; ``None``: none.
    timeout_seconds: int | None = None


class MessageContract(_Strict):
    """One message on igni's socket."""

    direction: Direction
    doc: str
    schema_: dict[str, Any] = Field(alias="schema")
    #: What igni takes of a message a client may send.
    accepts: dict[str, Any] | None = None


class PushChannelContract(_Strict):
    """One push notification channel: what its payload is."""

    doc: str = ""
    schema_: dict[str, Any] = Field(alias="schema")


class RpcContract(_Strict):
    """The whole file."""

    version: int
    defs: dict[str, dict[str, Any]]
    methods: dict[str, MethodContract]
    messages: dict[str, MessageContract]
    push_channels: dict[str, PushChannelContract] = Field(default_factory=dict)
    #: Which access level a connection reaches, and how it gets it: prose.
    access: str = ""
    #: The classes of how long a call takes, and a timeout for each.
    durations: dict[str, DurationContract] = Field(default_factory=dict)
    #: What each error code means.
    errors: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def read(cls, path: Path = CONTRACT_FILE) -> RpcContract:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def ref_name(self, schema: dict[str, Any]) -> str | None:
        """The def a ``{"$ref": "#/defs/X"}`` schema names, or ``None``."""
        ref = schema.get("$ref")
        if not isinstance(ref, str):
            return None
        name = ref.rsplit("/", 1)[-1]
        if name not in self.defs:
            raise KeyError(f"{ref} names no def")
        return name

    def message_def(self, wire_type: str) -> str:
        name = self.ref_name(self.messages[wire_type].schema_)
        if name is None:
            raise ValueError(f"message {wire_type} is not a $ref")
        return name


__all__ = [
    "CONTRACT_FILE",
    "PUSH_PREFIX",
    "Access",
    "Correlation",
    "Direction",
    "DurationContract",
    "MessageContract",
    "MethodContract",
    "PushChannelContract",
    "RpcContract",
    "Scope",
]
