"""Which of the contract's methods and defs igni-client gets, and where each method goes."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict

from tools.client_contract import PUSH_PREFIX, PushChannelContract, RpcContract
from tools.client_names import (
    FOLLOWED,
    MESSAGE_METHODS,
    MESSAGES_NOT_SENT,
    MESSAGES_SENT_BY_HAND,
    METHODS,
    NOT_FOR_CLIENTS,
    SCOPE_EXCEPTIONS,
    UNFOLLOWED,
)
from tools.client_python import ContractError, pascal
from tools.client_types import Types

#: The keys of a schema whose values are data, not schemas.
_DATA_KEYS = ("default", "const", "enum")


class Placement(BaseModel):
    """Where one method lives in Python: ``igni.processes.tail``."""

    model_config = ConfigDict(frozen=True)

    wire: str
    owner: str
    namespace: str
    name: str

    @classmethod
    def of(cls, wire: str, path: str) -> Placement:
        parts = path.split(".")
        if parts[0] not in ("igni", "session") or len(parts) not in (2, 3):
            raise ContractError(f"{wire}: {path!r} is not igni.<ns>.<name> or session.<ns>.<name>")
        namespace = parts[1] if len(parts) == 3 else ""
        return cls(wire=wire, owner=parts[0], namespace=namespace, name=parts[-1])

    @property
    def path(self) -> str:
        return ".".join(p for p in (self.owner, self.namespace, self.name) if p)

    @property
    def group(self) -> str:
        """``igni.processes``, or ``igni`` for a method on the client itself."""
        return ".".join(p for p in (self.owner, self.namespace) if p)


def class_for_group(group: str) -> str:
    """``igni.processes`` → ``IgniProcesses``; ``session`` → ``SessionApi``."""
    if "." not in group:
        return pascal(group) + "Api"
    return pascal(group)


def push_class(channel: str) -> str:
    """The class of a typed push: ``process_line`` → ``ProcessLinePush``."""
    return pascal(channel) + "Push"


def hoisted(contract: RpcContract) -> RpcContract:
    """``contract`` with every object it defines in place made a def of its own.

    A push channel's payload is sometimes written out where it is used,
    titled but not in ``defs``; as a def it becomes a class like any other.
    """
    contract = contract.model_copy(deep=True)

    def lift(node: Any) -> Any:
        if isinstance(node, list):
            return [lift(n) for n in node]
        if not isinstance(node, dict):
            return node
        node = {k: (v if k in _DATA_KEYS else lift(v)) for k, v in node.items()}
        if node.get("type") == "object" and "properties" in node and "title" in node:
            name = node["title"]
            if contract.defs.get(name, node) != node:
                # A def of that title is the broadcast; this is its payload, without `channel`.
                name = name.removesuffix("Event") + "Payload"
                if contract.defs.get(name, node) != node:
                    raise ContractError(f"{node['title']} is defined twice, differently")
            contract.defs[name] = node
            return {"$ref": f"#/defs/{name}"}
        return node

    for name, channel in list(contract.push_channels.items()):
        contract.push_channels[name] = PushChannelContract.model_validate(
            {"doc": channel.doc, "schema": lift(channel.schema_)}
        )
    return contract


class Plan:
    """Which methods and defs are generated, and where each method goes."""

    def __init__(self, contract: RpcContract) -> None:
        self.contract = hoisted(contract)
        self.types = Types(self.contract)
        self._check_placement()
        self.placements = {
            wire: Placement.of(wire, METHODS[wire])
            for wire in sorted(self.contract.methods)
            if wire not in NOT_FOR_CLIENTS
        }
        self._check_messages()
        self.defs_in, self.defs_out = self._reachable()

    def _check_placement(self) -> None:
        wires = set(self.contract.methods)
        unplaced = wires - set(METHODS) - set(NOT_FOR_CLIENTS)
        if unplaced:
            raise ContractError(
                f"methods with no name in tools/client_names.py: {sorted(unplaced)}"
            )
        gone = (set(METHODS) | set(NOT_FOR_CLIENTS)) - wires
        if gone:
            raise ContractError(f"tools/client_names.py names methods igni lacks: {sorted(gone)}")
        both = set(METHODS) & set(NOT_FOR_CLIENTS)
        if both:
            raise ContractError(f"both named and not for clients: {sorted(both)}")
        for wire, path in METHODS.items():
            method = self.contract.methods[wire]
            if method.access in ("page", "platform"):
                raise ContractError(f"{wire} is a {method.access} call; list it in NOT_FOR_CLIENTS")
            if path.split(".")[0] != method.scope and wire not in SCOPE_EXCEPTIONS:
                raise ContractError(
                    f"{wire} has scope {method.scope} but is placed at {path}; "
                    "place it by its scope or say why in SCOPE_EXCEPTIONS"
                )
        streaming = {
            w for w, m in self.contract.methods.items() if m.streams or m.may_stream
        } - set(NOT_FOR_CLIENTS)
        decided = set(FOLLOWED) | set(UNFOLLOWED)
        if streaming != decided:
            raise ContractError(
                "every method that causes events is either followed or says why not: "
                f"undecided {sorted(streaming - decided)}, "
                f"not causing events {sorted(decided - streaming)}"
            )
        paths = [Placement.of(w, p).path for w, p in METHODS.items()]
        clashes = {p for p in paths if paths.count(p) > 1}
        if clashes:
            raise ContractError(f"two methods share a name: {sorted(clashes)}")

    def _check_messages(self) -> None:
        sent = {t for t, m in self.contract.messages.items() if m.direction in ("to_igni", "both")}
        decided = set(MESSAGE_METHODS) | set(MESSAGES_NOT_SENT) | set(MESSAGES_SENT_BY_HAND)
        if sent != decided:
            raise ContractError(
                "every message a client may send is a method, sent by hand, or says why "
                f"not: undecided {sorted(sent - decided)}, unknown {sorted(decided - sent)}"
            )

    def _reachable(self) -> tuple[set[str], set[str]]:
        """The defs a client sends (``in``) and reads (``out``)."""
        inputs: list[dict[str, Any]] = []
        outputs: list[dict[str, Any]] = []
        for wire in self.placements:
            method = self.contract.methods[wire]
            inputs.append(method.args)
            outputs.append(method.result)
        for message in self.contract.messages.values():
            if message.direction in ("to_igni", "both"):
                inputs.append(message.schema_)
            if message.direction in ("to_client", "both"):
                outputs.append(message.schema_)
        for channel in self.contract.push_channels.values():
            outputs.append(channel.schema_)
        return self._closure(inputs), self._closure(outputs)

    def _closure(self, roots: Iterable[dict[str, Any]]) -> set[str]:
        found: set[str] = set()
        stack: list[Any] = list(roots)
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                ref = self.contract.ref_name(node)
                if ref is not None and ref not in found:
                    found.add(ref)
                    stack.append(self.contract.defs[ref])
                stack.extend(v for k, v in node.items() if k not in _DATA_KEYS)
            elif isinstance(node, list):
                stack.extend(node)
        found.discard("JsonValue")
        return found

    def groups(self) -> dict[str, list[Placement]]:
        """Every method a client calls, the messages sent as methods among them, by group."""
        groups: dict[str, list[Placement]] = {}
        placements = [
            *self.placements.values(),
            *(Placement.of(name, path) for name, (_, path) in MESSAGE_METHODS.items()),
        ]
        for placement in placements:
            groups.setdefault(placement.group, []).append(placement)
        return groups

    # ── Messages ──

    def message_of_def(self) -> dict[str, str]:
        """Def name → the wire type of the message it is."""
        return {self.contract.message_def(t): t for t in self.contract.messages}

    def stream_classes(self, wire: str) -> list[str]:
        """The classes of what ``wire`` streams, in the contract's order."""
        return self._classes(self.contract.methods[wire].streams)

    def event_classes(self, wire: str) -> list[str]:
        """The classes of what ``wire`` causes: what it streams, and what may
        be pushed while it runs.

        A call's events are what it causes, not only what it streams: a run
        that goes on after the call answers still pushes what its tools do.
        """
        method = self.contract.methods[wire]
        return self._classes((*method.streams, *method.may_stream))

    def _classes(self, streams: Iterable[str]) -> list[str]:
        out: list[str] = []
        for stream in streams:
            if stream.startswith(PUSH_PREFIX):
                channel = stream.removeprefix(PUSH_PREFIX)
                name = (
                    push_class(channel)
                    if channel in self.contract.push_channels
                    else "PushNotification"
                )
            else:
                name = self.types.class_name(self.contract.message_def(stream))
            if name not in out:
                out.append(name)
        return out


__all__ = ["Placement", "Plan", "class_for_group", "hoisted", "push_class"]
