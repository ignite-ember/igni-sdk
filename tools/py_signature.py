"""A Python callable's signature, written as the reference pages show it.

``inspect`` reports a callable's parameters; this module writes them the
way the source spells them: the signature line under a name's heading,
and the table of its parameters under that (``tools/py_reference.py``).
A parameter named ``_like_this`` belongs to a library, not to the
callable's caller, and is in neither.
"""

from __future__ import annotations

import enum
import inspect
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from tools.param_docs import UNDOCUMENTED, ParameterRow, code, table


def stable_repr(value: Any) -> str:
    """``repr(value)``, the same on every run: sets sorted, no addresses."""
    if isinstance(value, frozenset | set):
        items = ", ".join(sorted(stable_repr(v) for v in value))
        name = type(value).__name__
        return f"{name}({{{items}}})" if items else f"{name}()"
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    text = re.sub(r" at 0x[0-9a-fA-F]+", "", repr(value))
    # `igni_service.tokens.Person | …` reads as `Person | …`, as the code spells it.
    return re.sub(r"\b[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+\.(?=[A-Z])", "", text)


def annotation_text(annotation: Any) -> str:
    """An annotation as its source spells it, where ``from __future__`` kept it a string."""
    if annotation is inspect.Parameter.empty:
        return ""
    if isinstance(annotation, str):
        return annotation
    if isinstance(annotation, type):
        return annotation.__qualname__
    return re.sub(r"\b(typing|collections\.abc|builtins)\.", "", repr(annotation))


def type_name(value: Any) -> str:
    """The type a constant's line names: its class, or ``type`` for a generic alias."""
    if hasattr(value, "__origin__"):
        return "type"
    return annotation_text(type(value))


def _is_private(param: inspect.Parameter) -> bool:
    """A parameter named ``_like_this`` is not one a caller passes.

    pydantic-settings adds ``_env_file`` and a dozen like it to a settings
    class's constructor; they belong to the library, not to the class.
    """
    return param.name.startswith("_") and param.kind not in (
        param.VAR_POSITIONAL,
        param.VAR_KEYWORD,
    )


def _star(param: inspect.Parameter) -> str:
    """The stars a parameter is written with: ``*args``, ``**kwargs``, or none."""
    if param.kind is param.VAR_POSITIONAL:
        return "*"
    if param.kind is param.VAR_KEYWORD:
        return "**"
    return ""


def _default_cell(param: inspect.Parameter) -> str:
    """What the table says a parameter defaults to."""
    if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
        return "—"
    if param.default is inspect.Parameter.empty:
        return "required"
    return code(stable_repr(param.default))


class CallableSignature(BaseModel):
    """The parameters a callable's caller passes, and what it returns.

    ``known`` is false for what ``inspect`` cannot read a signature from;
    its parameters are then written ``…``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    parameters: list[inspect.Parameter]
    #: The return annotation as the source spells it; empty when there is none.
    returns: str = ""
    known: bool = True

    @classmethod
    def of(cls, obj: Any, *, skip_self: bool = False) -> CallableSignature:
        """``obj``'s signature, without ``self`` or ``cls`` when ``skip_self``."""
        try:
            sig = inspect.signature(obj)
        except (TypeError, ValueError):
            return cls(parameters=[], known=False)
        params = list(sig.parameters.values())
        if skip_self and params and params[0].name in ("self", "cls"):
            params = params[1:]
        return cls(
            parameters=[param for param in params if not _is_private(param)],
            returns=annotation_text(sig.return_annotation),
        )

    def text(self) -> str:
        """The parameters as the ``def`` line spells them, ``/`` and ``*`` included."""
        if not self.known:
            return "…"
        parts: list[str] = []
        seen_keyword_only = False
        params = self.parameters
        for index, param in enumerate(params):
            if param.kind is param.KEYWORD_ONLY and not seen_keyword_only:
                parts.append("*")
                seen_keyword_only = True
            if param.kind is param.VAR_POSITIONAL:
                seen_keyword_only = True
            parts.append(self._parameter_text(param))
            if param.kind is param.POSITIONAL_ONLY and (
                index + 1 == len(params) or params[index + 1].kind is not param.POSITIONAL_ONLY
            ):
                parts.append("/")
        return ", ".join(parts)

    def arrow(self) -> str:
        """`` -> returns``, or nothing when there is no return annotation."""
        return f" -> {self.returns}" if self.returns else ""

    def table(self, meanings: dict[str, str]) -> list[str]:
        """The table of the parameters, each one's meaning read from ``meanings``.

        The meaning of each parameter is what the docstring's ``Args:``
        section says of it. A parameter the docstring does not document is
        said to be undocumented: the generator does not guess.
        """
        return table([self._row(param, meanings) for param in self.parameters])

    @staticmethod
    def _row(param: inspect.Parameter, meanings: dict[str, str]) -> ParameterRow:
        annotation = annotation_text(param.annotation)
        return ParameterRow(
            name=_star(param) + param.name,
            type=code(annotation) if annotation else "—",
            default=_default_cell(param),
            meaning=meanings.get(param.name) or UNDOCUMENTED,
        )

    @staticmethod
    def _parameter_text(param: inspect.Parameter) -> str:
        text = _star(param) + param.name
        ann = annotation_text(param.annotation)
        if ann:
            text += f": {ann}"
        if param.default is not inspect.Parameter.empty:
            text += f" = {stable_repr(param.default)}" if ann else f"={stable_repr(param.default)}"
        return text


__all__ = ["CallableSignature", "annotation_text", "stable_repr", "type_name"]
