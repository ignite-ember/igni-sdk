"""`ext.tools`: the tools an extension registers, the names each goes by, and their manifest lines."""

from __future__ import annotations

import contextlib
import functools
from collections.abc import Callable, Iterator
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict

from igni_extension.caller import CallerScope
from igni_extension.hints import ToolHints, ToolHintsMissing
from igni_extension.mcp_server import ExtensionMcpServer
from igni_extension.threads import OffTheLoop

AnyFunction = Callable[..., Any]

ToolObserver = Callable[[str], contextlib.AbstractContextManager[Any]]
"""Entered around each tool call, given the tool's name, in the call's context."""


class ToolNames(BaseModel):
    """Every name one tool goes by, from where each is written.

    `tool` is the name in this code (the function's, or `name=`); the
    others are derived from it and the extension's id, by igni's rules.
    """

    model_config = ConfigDict(use_attribute_docstrings=True)

    tool: str
    """What `ext.tool` registered, and `HostHarness.call` takes."""
    manifest: str
    """The manifest's `permissions.tools[].name` (and `permissions.rpc` is
    `rpc` below): namespaced by the extension's id, so an administrator
    reading it knows whose tool it is.
    """
    rpc: str
    """What a page calls with `bridge.rpc(...)`, and `permissions.rpc` grants."""
    registered: str
    """What igni registers it as for its agent, and the name its permission
    rules and settings-file hooks match: `mcp_ext:<id>_<tool>`.
    """

    @classmethod
    def of(cls, extension_id: str, tool: str) -> ToolNames:
        """Every name the tool `tool` of the extension `extension_id` goes by."""
        return cls(
            tool=tool,
            manifest=f"{extension_id}.{tool}",
            rpc=f"ext.{extension_id}.{tool}",
            registered=f"mcp_ext:{extension_id}_{tool}",
        )


class ManifestTool(BaseModel):
    """One `permissions.tools` entry: the tool's namespaced name and its four hints.

    Dumped `by_alias`, the hints are spelled as MCP and a manifest spell them
    (`readOnlyHint`, ...).
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    name: str
    """The tool's namespaced name: `<extension id>.<tool>`."""
    annotations: ToolAnnotations
    """Its four hints, as MCP spells them."""

    def wire(self) -> dict[str, Any]:
        """The entry as the manifest's JSON spells it."""
        return self.model_dump(by_alias=True, exclude_none=True)


class ToolFailure:
    """A tool's exception as igni — and the model — reads it: its own message.

    `mcp` 2 sends only "Error executing tool" for an exception that is not
    a `ToolError`, which tells nobody what went wrong.
    """

    @staticmethod
    def in_its_own_words(error: Exception) -> ToolError:
        if isinstance(error, ToolError):
            return error
        return ToolError(str(error) or type(error).__name__)


class ToolRegistry:
    """The tools `ext.tool` registered on the extension's MCP server, with their hints."""

    def __init__(self, extension_id: str, mcp: ExtensionMcpServer) -> None:
        self._extension_id = extension_id
        self._mcp = mcp
        #: What each registered tool says it is, by its name.
        self._hints: dict[str, ToolHints] = {}
        #: Told of every call to a registered tool, around it, in the call's
        #: own context — what `testing.ConcurrencyHarness` watches.
        self._observers: list[ToolObserver] = []

    def tool(
        self,
        *,
        hints: ToolHints,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable[[AnyFunction], AnyFunction]:
        """Register a tool igni can call (`IgniExtension.tool`)."""
        register = self._mcp.tool(
            name=name, description=description, annotations=hints.annotations()
        )

        def registered(fn: AnyFunction) -> AnyFunction:
            tool = name or fn.__name__
            # `lookup_ticket.manifest_name`: the line `permissions.tools` needs.
            # Named before registering, so nothing is ever left half registered.
            self._name(fn, ToolNames.of(self._extension_id, tool).manifest)
            # A parameter typed `Caller` is filled from the call, and is not
            # part of the tool's input (`igni_extension.caller`).
            register(self._observed(tool, CallerScope.inject(fn)))
            self._hints[tool] = hints
            return fn

        return registered

    @staticmethod
    def _name(fn: AnyFunction, manifest_name: str) -> None:
        """Hang `manifest_name` on `fn`, where it can carry one.

        A bound method keeps its attributes on the function it binds
        (`__func__`) and reads them from there. A callable that takes no
        attributes at all (a builtin, a `__slots__` object) is registered
        without the convenience: `ext.tools.names(tool)` still answers.
        """
        with contextlib.suppress(AttributeError, TypeError):
            setattr(getattr(fn, "__func__", fn), "manifest_name", manifest_name)  # noqa: B010

    def _observed(self, tool: str, fn: AnyFunction) -> AnyFunction:
        """`fn` as the server runs it: observed, and failing in its own words.

        A plain `def` stays plain, so `mcp` still runs it in a worker thread.
        """
        observers = self._observers

        if OffTheLoop.is_async(fn):

            @functools.wraps(fn)
            async def observed_async(*args: Any, **kwargs: Any) -> Any:
                with contextlib.ExitStack() as stack:
                    for observer in list(observers):
                        stack.enter_context(observer(tool))
                    try:
                        return await fn(*args, **kwargs)
                    except Exception as error:
                        raise ToolFailure.in_its_own_words(error) from error

            return observed_async

        @functools.wraps(fn)
        def observed(*args: Any, **kwargs: Any) -> Any:
            with contextlib.ExitStack() as stack:
                for observer in list(observers):
                    stack.enter_context(observer(tool))
                try:
                    return fn(*args, **kwargs)
                except Exception as error:
                    raise ToolFailure.in_its_own_words(error) from error

        return observed

    @contextlib.contextmanager
    def observing(self, observer: ToolObserver) -> Iterator[None]:
        """Tell `observer` of every tool call for as long as the block runs."""
        self._observers.append(observer)
        try:
            yield
        finally:
            self._observers.remove(observer)

    def names(self, tool: str) -> ToolNames:
        """Every name `tool` goes by: in code, in the manifest, from a page, in igni.

        `KeyError` for a tool this extension does not register.
        """
        if tool not in self._hints:
            known = ", ".join(sorted(self._hints))
            raise KeyError(
                f"{self._extension_id} registers no tool {tool!r} (it has: {known or 'none'})"
            )
        return ToolNames.of(self._extension_id, tool)

    def manifest(self) -> list[ManifestTool]:
        """`permissions.tools` as the code states it: each tool's namespaced name and hints.

        What `igni-service-bundle` writes into the bundle's manifest when
        the extension's own leaves `permissions.tools` out, so the hints
        are stated once, here. `python -m igni_extension.manifest <module>`
        prints it. It lists the tools `ext.tool` registered; a tool added on
        `ext.mcp` directly is declared in the manifest by hand (and `check`
        still holds it to the four hints).
        """
        return [
            ManifestTool(
                name=ToolNames.of(self._extension_id, tool).manifest,
                annotations=hints.annotations(),
            )
            for tool, hints in sorted(self._hints.items())
        ]

    async def check(self) -> None:
        """Refuse to serve a tool that leaves one of its four hints unstated.

        A tool registered on `ext.mcp` directly, rather than through
        `ext.tool`, is checked the same way.
        """
        ToolHintsMissing.check(await self._mcp.list_tools())
