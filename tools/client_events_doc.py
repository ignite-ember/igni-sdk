"""igni-client's events reference page: every message igni sends and a client sends,
and every push notification channel's payload, field by field."""

from __future__ import annotations

from pydantic import BaseModel, Field

from tools.client_doc_layout import CLIENT_PACKAGE, EVENTS_PAGE
from tools.client_doc_links import ClientSources
from tools.client_model_fields import ModelFields
from tools.client_names import MESSAGE_METHODS, MESSAGES_NOT_SENT, MESSAGES_SENT_BY_HAND
from tools.client_plan import push_class
from tools.client_python import Imports
from tools.markdown_pages import tidy
from tools.site_page import REFERENCE, Page
from tools.wire_prose import rst

_INTRO = [
    "Every message on igni's socket and every push notification channel, as "
    "igni-client types them (`igni_client.models`, re-exported in "
    "`igni_client.events` and `igni_client.frames`). Messages igni sends are "
    "`Event`s — `type`, `id`, `session_id` and `event_seq` on each — and a run's "
    "are `RunEvent`s, which carry `run_id` and `parent_run_id` besides. A push "
    "notification on a channel the contract types is that channel's "
    "`PushNotification` subclass, its `payload` typed. A message newer than this "
    "igni-client arrives as `Unknown`, with everything it carried.",
    "",
    "Read them from `session.send()` (a run), `session.events()` and "
    "`igni.events()` (everything), or a followed call's `async for`.",
    "",
]


class MessageKinds(BaseModel):
    """The contract's messages by who sends them: a run's events, igni's other
    messages, and what a client sends."""

    run_events: list[str] = Field(default_factory=list)
    other: list[str] = Field(default_factory=list)
    sent: list[str] = Field(default_factory=list)


class EventsPage:
    """The events reference page."""

    def __init__(self, sources: ClientSources, fields: ModelFields) -> None:
        self.sources = sources
        self.fields = fields
        #: Each event class → the methods that stream it.
        self.streamed_by = self._streamed_by()

    def _streamed_by(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for wire in sorted(self.sources.plan.placements):
            for cls in self.sources.plan.stream_classes(wire):
                out.setdefault(cls, []).append(wire)
        return out

    def _kinds(self) -> MessageKinds:
        contract, types = self.sources.contract, self.sources.types
        kinds = MessageKinds()
        for wire_type in sorted(
            contract.messages, key=lambda t: types.class_name(contract.message_def(t))
        ):
            message = contract.messages[wire_type]
            props = contract.defs[contract.message_def(wire_type)].get("properties", {})
            if message.direction in ("to_client", "both"):
                if all(f in props for f in ("run_id", "parent_run_id")):
                    kinds.run_events.append(wire_type)
                else:
                    kinds.other.append(wire_type)
            if message.direction in ("to_igni", "both"):
                kinds.sent.append(wire_type)
        return kinds

    def page(self, order: int) -> Page:
        kinds = self._kinds()
        body = [*_INTRO, "## Events of a run", ""]
        for wire_type in kinds.run_events:
            body += self._message(wire_type)
        body += ["## Other messages igni sends", ""]
        for wire_type in kinds.other:
            body += self._message(wire_type)
        body += self._push_notifications()
        body += ["## Messages a client sends", ""]
        for wire_type in kinds.sent:
            body += self._message(wire_type, how=self._how_sent(wire_type))
        return Page(
            CLIENT_PACKAGE,
            EVENTS_PAGE,
            "Events reference",
            "Every message igni sends and a client sends, and every push notification "
            "channel's payload, field by field.",
            REFERENCE,
            order,
            tidy(body),
            source="contracts/rpc-contract.json",
        )

    def _how_sent(self, wire_type: str) -> str:
        if wire_type in MESSAGE_METHODS:
            return f"igni-client sends it as {self.sources.layout.method_link(wire_type)}."
        if wire_type in MESSAGES_SENT_BY_HAND:
            return f"igni-client sends it from {rst(MESSAGES_SENT_BY_HAND[wire_type])}."
        return f"igni-client does not send it: {rst(MESSAGES_NOT_SENT[wire_type])}."

    def _push_notifications(self) -> list[str]:
        contract = self.sources.contract
        out = [
            "## Push notifications",
            "",
            "Each arrives as a `push_notification` message on its channel; its class is "
            "named for the channel, and its `payload` is the model linked.",
            "",
        ]
        for channel in sorted(contract.push_channels):
            spec = contract.push_channels[channel]
            cls = push_class(channel)
            payload = self.sources.types.annotation(spec.schema_, Imports())
            out += [f"### {cls}", ""]
            if spec.doc:
                out += [rst(spec.doc), ""]
            out += [f"Channel `{channel}`; `payload` is {self.sources.type_md(payload)}.", ""]
            ref = contract.ref_name(spec.schema_)
            if ref is not None and contract.defs[ref].get("properties"):
                out += self.fields.table(ref)
            out += self._streamed(cls)
        return out

    def _streamed(self, cls: str) -> list[str]:
        if cls not in self.streamed_by:
            return []
        links = ", ".join(self.sources.layout.method_link(w) for w in self.streamed_by[cls])
        return [f"**Streamed by** {links}.", ""]

    def _message(self, wire_type: str, how: str = "") -> list[str]:
        contract = self.sources.contract
        def_name = contract.message_def(wire_type)
        cls = self.sources.types.class_name(def_name)
        doc = contract.defs[def_name].get("description") or contract.messages[wire_type].doc
        out = [f"### {cls}", ""]
        if doc:
            out += [rst(doc), ""]
        out += [f"Wire type `{wire_type}`." + (f" {how}" if how else ""), ""]
        out += self.fields.table(def_name)
        out += self._streamed(cls)
        return out


__all__ = ["EventsPage", "MessageKinds"]
