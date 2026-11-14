"""igni-client's method pages, a page per area, and the access page: who may call what."""

from __future__ import annotations

from tools.client_doc_layout import ACCESS_PAGE, CLIENT_PACKAGE
from tools.client_doc_links import ClientSources
from tools.client_method_doc import MethodSection
from tools.client_names import (
    MESSAGE_DOCS,
    MESSAGE_METHODS,
    MESSAGES_NOT_SENT,
    NAMESPACES,
    NOT_FOR_CLIENTS,
    OWNER_DOCS,
)
from tools.client_plan import class_for_group
from tools.markdown_pages import first_sentences, tidy
from tools.site_page import REFERENCE, Page, url
from tools.wire_prose import cell, rst


class MethodPages:
    """The reference pages of igni-client's methods, one per area."""

    def __init__(self, sources: ClientSources, sections: MethodSection) -> None:
        self.sources = sources
        self.sections = sections

    def pages(self, start: int) -> list[Page]:
        layout = self.sources.layout
        pages: list[Page] = []
        for index, (slug, title, _) in enumerate(layout.pages):
            wires = layout.on_page(slug)
            groups = list(dict.fromkeys(layout.placements[w].group for w in wires))
            about = [NAMESPACES.get(g) or OWNER_DOCS[g] for g in groups]
            out = self._where(groups)
            out += [
                "Every method here is generated from igni-core's RPC contract; its "
                "documentation is igni's own. The examples run inside an `async` function "
                "with `igni` an open `IgniClient` and `session` one of its sessions "
                f"([Quick start]({url(CLIENT_PACKAGE, 'quick-start')})).",
                "",
                "| Method | What it does |",
                "|---|---|",
            ]
            for wire in wires:
                out.append(f"| {layout.method_link(wire)} | {cell(self._summary(wire))} |")
            out.append("")
            for wire in wires:
                out += self.sections.section(wire)
            description = first_sentences(" ".join(rst(a) for a in dict.fromkeys(about)))
            pages.append(
                Page(
                    CLIENT_PACKAGE,
                    slug,
                    title,
                    description,
                    REFERENCE,
                    start + index,
                    tidy(out),
                    source="contracts/rpc-contract.json and tools/client_names.py",
                )
            )
        return pages

    def _summary(self, wire: str) -> str:
        contract = self.sources.contract
        if wire in MESSAGE_METHODS:
            doc = MESSAGE_DOCS.get(wire, contract.messages[wire].doc)
            return rst(doc.strip().split("\n\n")[0])
        return rst(contract.methods[wire].summary)

    @staticmethod
    def _where(groups: list[str]) -> list[str]:
        out: list[str] = []
        for group in groups:
            owner = "IgniClient" if group.startswith("igni") else "Session"
            if "." in group:
                attr = group.split(".", 1)[1]
                out.append(f"- `{group}` — `{owner}.{attr}`, a `{class_for_group(group)}`")
            else:
                out.append(f"- `{group}` — on `{owner}` itself")
        return ["Where these methods are:", "", *out, ""]


class AccessPage:
    """The page of which connections may make each call."""

    def __init__(self, sources: ClientSources) -> None:
        self.sources = sources

    def _by_access(self) -> dict[str, list[str]]:
        """Each access → links to the methods that need it, by path."""
        layout, contract = self.sources.layout, self.sources.contract
        out: dict[str, list[str]] = {}
        for wire, _ in sorted(layout.placements.items(), key=lambda x: x[1].path):
            access = "client" if wire in MESSAGE_METHODS else contract.methods[wire].access
            out.setdefault(access, []).append(layout.method_link(wire))
        return out

    def page(self, order: int) -> Page:
        body = [
            "Each method says which connections may call it: its **access**. "
            "igni-client checks it before sending where it knows the connection's "
            f"standing, and raises {self.sources.type_md('AccessRefused')} — the error igni "
            "would answer.",
            "",
            "## Who may call what",
            "",
            rst(self.sources.contract.access),
            "",
            "## The access each method needs",
            "",
            "| Access | Methods |",
            "|---|---|",
        ]
        by_access = self._by_access()
        for access in ("window", "approver"):
            if access in by_access:
                body.append(f"| `{access}` | {', '.join(by_access[access])} |")
        body += ["", "Every other method needs only `client`.", ""]
        body += [
            "## Not for clients",
            "",
            "igni's methods and messages that igni-client does not offer, and why.",
            "",
            "| Wire method | Why |",
            "|---|---|",
        ]
        body += [f"| `{w}` | {cell(r)} |" for w, r in sorted(NOT_FOR_CLIENTS.items())]
        body += ["", "| Message | Why a client does not send it |", "|---|---|"]
        body += [f"| `{w}` | {cell(r)} |" for w, r in sorted(MESSAGES_NOT_SENT.items())]
        return Page(
            CLIENT_PACKAGE,
            ACCESS_PAGE,
            "Access: who may call what",
            "Which connections may make each call — client, approver, window — and how a "
            "connection's standing is decided.",
            REFERENCE,
            order,
            tidy(body),
            source="contracts/rpc-contract.json",
        )


__all__ = ["AccessPage", "MethodPages"]
