"""What igni-client's reference pages render from, and where each type it names links.

``ClientSources`` is the one bundle every page renderer takes: the
generator's plan, the generated API's signatures, where each method is, the
links of every documented type, and the contract's prose said the Python way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tools.client_api import ApiGenerator
from tools.client_contract import RpcContract
from tools.client_doc_layout import (
    CLIENT_PACKAGE,
    ERRORS_PAGE,
    EVENTS_PAGE,
    MODELS_PAGE,
    ClientLayout,
)
from tools.client_errors_doc import ErrorCatalog
from tools.client_names import FOLLOWED
from tools.client_plan import Plan, push_class
from tools.client_types import Types
from tools.markdown_pages import ReadmePages, plain, site_id
from tools.site_page import url
from tools.wire_prose import WireProse

_IDENTIFIER = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)")


class ClientLinks:
    """Every type the reference documents → the page and heading it is on."""

    def __init__(
        self,
        layout: ClientLayout,
        api: ApiGenerator,
        errors: ErrorCatalog,
        readme: ReadmePages,
    ) -> None:
        self.links = self._links(layout, api, errors)
        call = self._readme_anchor(readme, "API reference", "Call")
        if call:
            self.links["Call"] = call

    @staticmethod
    def _links(layout: ClientLayout, api: ApiGenerator, errors: ErrorCatalog) -> dict[str, str]:
        plan = layout.plan
        contract, types = plan.contract, plan.types
        messages = layout.messages
        links: dict[str, str] = {}
        for name in sorted(plan.defs_in | plan.defs_out):
            page = EVENTS_PAGE if name in messages else MODELS_PAGE
            cls = types.class_name(name)
            links[cls] = url(CLIENT_PACKAGE, page, site_id(cls))
        # An argument model's fields are its method's parameters: it links there.
        for wire in plan.placements:
            args = contract.ref_name(contract.methods[wire].args)
            if args is not None:
                links[types.class_name(args)] = layout.method_url(wire)
        for channel in contract.push_channels:
            cls = push_class(channel)
            links[cls] = url(CLIENT_PACKAGE, EVENTS_PAGE, site_id(cls))
        for alias in types.unions:
            links[alias] = url(CLIENT_PACKAGE, MODELS_PAGE, site_id(alias))
        for name, _ in errors.items():
            links[name] = url(CLIENT_PACKAGE, ERRORS_PAGE, site_id(name))
        for wire in FOLLOWED:
            links[api.event_alias(wire)] = layout.method_url(wire)
        return links

    @staticmethod
    def _readme_anchor(readme: ReadmePages, section: str, heading: str) -> str | None:
        for h in readme.headings:
            if h.section == section and plain(h.text) == heading and h.level > 2:
                return url(CLIENT_PACKAGE, site_id(section), site_id(h.text))
        return None

    def type_md(self, annotation: str, *, in_table: bool = False) -> str:
        """An annotation in code, with every type the reference documents linked."""
        annotation = annotation.replace("builtins.", "")
        out: list[str] = []
        pending = ""
        for part in _IDENTIFIER.split(annotation):
            if part in self.links:
                if pending:
                    out.append(f"`{pending}`")
                    pending = ""
                out.append(f"[`{part}`]({self.links[part]})")
            else:
                pending += part
        if pending:
            out.append(f"`{pending}`")
        text = "".join(out)
        return text.replace("|", "\\|") if in_table else text


@dataclass(frozen=True)
class ClientSources:
    """What every page of igni-client's reference renders from."""

    api: ApiGenerator
    layout: ClientLayout
    links: ClientLinks
    prose: WireProse

    @classmethod
    def build(
        cls, contract: RpcContract, errors: ErrorCatalog, readme: ReadmePages
    ) -> ClientSources:
        plan = Plan(contract)
        api = ApiGenerator(plan)
        # Generating the API names the unions the models use.
        api.generate()
        layout = ClientLayout(plan)
        return cls(
            api=api,
            layout=layout,
            links=ClientLinks(layout, api, errors, readme),
            prose=WireProse(plan.contract, layout.placements),
        )

    @property
    def plan(self) -> Plan:
        return self.layout.plan

    @property
    def contract(self) -> RpcContract:
        return self.layout.plan.contract

    @property
    def messages(self) -> dict[str, str]:
        """Def name → the wire type of the message it is."""
        return self.layout.messages

    @property
    def types(self) -> Types:
        return self.layout.plan.types

    def type_md(self, annotation: str, *, in_table: bool = False) -> str:
        return self.links.type_md(annotation, in_table=in_table)


__all__ = ["ClientLinks", "ClientSources"]
