"""The notes under a method's signature: its events, how long it takes, who may call
it and what it raises, each as igni-core's contract says."""

from __future__ import annotations

from tools.client_contract import PUSH_PREFIX
from tools.client_doc_layout import ACCESS_PAGE, CLIENT_PACKAGE, ERRORS_PAGE
from tools.client_doc_links import ClientSources
from tools.client_errors_doc import ErrorCatalog
from tools.client_names import ACCESS_NOTES, FOLLOWED, UNFOLLOWED
from tools.site_page import DocsError, url
from tools.wire_prose import rst


def place_text(by: str) -> str:
    """How the contract's place in a message is said: where the value a call is told
    apart by is."""
    match by:
        case "id":
            return "the message's own id"
        case "session_id":
            return "the session the message is for"
        case "run_id":
            return "the run the message is of"
        case "channel":
            return "the channel the message is on"
    return f"the message's `{by.removeprefix('payload.')}`"


def source_text(source: str) -> str:
    """How the contract's place in a call is said: where the value comes from."""
    match source:
        case "request.id":
            return "the id the call was sent as"
        case "request.session_id":
            return "the session the call was for"
    kind, dot, name = source.partition(".")
    if dot and kind == "args":
        return f"the `{name}` the call was given"
    if dot and kind == "result":
        return f"the `{name}` the call was answered with"
    return f"the call's `{source}`"


def _channels(streams: tuple[str, ...] | list[str]) -> str:
    return ", ".join(f"`{s.removeprefix(PUSH_PREFIX)}`" for s in streams)


class MethodNotes:
    """The bold-labelled notes of one method's section."""

    def __init__(self, sources: ClientSources, errors: ErrorCatalog) -> None:
        self.sources = sources
        self.errors = errors

    def streams(self, wire: str) -> list[str]:
        """What the call streams and may cause, and how its own events are told apart."""
        method = self.sources.contract.methods.get(wire)
        if method is None:
            return []
        out: list[str] = []
        if method.streams:
            classes = self.sources.plan.event_classes(wire)
            linked = ", ".join(self.sources.type_md(c) for c in classes)
            channels = _channels(method.streams)
            if wire in FOLLOWED:
                alias = self.sources.api.event_alias(wire)
                out += [f"**Events** `{alias}` is any of {linked} (igni streams {channels}).", ""]
            else:
                out += [
                    f"**Events** while it runs igni also streams {channels} ({linked}). "
                    f"This call does not follow them: {rst(UNFOLLOWED[wire])}",
                    "",
                ]
        if method.may_stream:
            out += [
                f"**While it runs** it may also cause these pushes: {_channels(method.may_stream)}.",
                "",
            ]
        if wire in FOLLOWED:
            out += [f"**How they are told apart** {rst(FOLLOWED[wire])}", ""]
        out += self.told_apart(wire)
        return out

    def told_apart(self, wire: str) -> list[str]:
        """How the contract says the call's own events are told from every other call's."""
        method = self.sources.contract.methods.get(wire)
        correlate = method.correlate if method is not None else None
        if correlate is None:
            return []
        place = place_text(correlate.by)
        if correlate.equals:
            return [
                f"**Told apart by** {place} is `{correlate.equals}` — igni's contract says so.",
                "",
            ]
        if correlate.source:
            source = source_text(correlate.source)
            return [f"**Told apart by** {place} is {source} — igni's contract says so.", ""]
        return [f"**Told apart by** {place}, and by what the call causes.", ""]

    def duration(self, wire: str) -> list[str]:
        """How long the call takes, and how long the client waits for it."""
        contract = self.sources.contract
        method = contract.methods.get(wire)
        if method is None or not method.duration:
            return []
        duration = contract.durations.get(method.duration)
        what = rst(duration.doc) if duration is not None else f"`{method.duration}`"
        out = [f"**How long** `{method.duration}` — {what}"]
        if method.timeout_seconds is None:
            out.append("The client waits as long as it takes.")
        else:
            out.append(f"The client waits up to {method.timeout_seconds} seconds.")
        out.append("")
        return out

    @staticmethod
    def access(access: str) -> list[str]:
        link = url(CLIENT_PACKAGE, ACCESS_PAGE)
        if access == "client":
            return [f"**Access** [`client`]({link}) — any connection igni admitted.", ""]
        note = rst(ACCESS_NOTES[access]).removeprefix(f"Access: `{access}`. ")
        return [f"**Access** [`{access}`]({link}) — {note}", ""]

    def raises(self, access: str, *, followed: bool, sends_only: bool) -> list[str]:
        names = ["InvalidArguments"]
        if access != "client":
            names.append("AccessRefused")
        if not sends_only:
            names += ["MethodFailed", "UnknownMethod", "UnexpectedAnswer"]
        names.append("Unavailable")
        if followed:
            names.append("RunInterrupted")
        parts = [self._raised(name, access) for name in names]
        return [
            "**Raises** "
            + " · ".join(parts)
            + f" ([when each is raised]({url(CLIENT_PACKAGE, ERRORS_PAGE)}))",
            "",
        ]

    def _raised(self, name: str, access: str) -> str:
        if name not in self.errors:
            raise DocsError(f"igni-client has no {name} to document")
        link = self.sources.type_md(name)
        if name == "AccessRefused":
            return link + f" when this connection does not stand as `{access}`"
        if name == "RunInterrupted":
            return link + " when the connection moves or drops while the call is followed"
        return link


__all__ = ["MethodNotes", "place_text", "source_text"]
