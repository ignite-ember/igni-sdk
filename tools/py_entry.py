"""One public name of a Python package: what it is, where it is defined, its heading."""

from __future__ import annotations

import inspect
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from tools.markdown_pages import site_id

#: What a public name is, which decides how its section is written.
EntryKind = Literal["class", "function", "constant"]


class Entry(BaseModel):
    """A name in a module's ``__all__``, and the object it names."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    obj: Any
    #: The ``__all__`` it is exported from: ``igni_service``, ``igni_service.testing``.
    exported_from: str

    @property
    def kind(self) -> EntryKind:
        if inspect.isclass(self.obj):
            return "class"
        if inspect.isfunction(self.obj):
            return "function"
        return "constant"

    @property
    def key(self) -> str:
        """``module:Name``: how an area names a constant, which has no module of its own."""
        return f"{self.exported_from}:{self.name}"

    @property
    def home(self) -> str:
        """The module that defines the name, or ``module:Name`` for a constant."""
        if self.kind == "constant":
            return self.key
        return str(self.obj.__module__)

    @property
    def title(self) -> str:
        """The heading of the name's section: a function's has ``()``."""
        return f"{self.name}()" if self.kind == "function" else self.name

    @property
    def anchor(self) -> str:
        return site_id(self.title)

    def taken_by(self, source: str) -> bool:
        """Whether an area's ``source`` takes this name.

        A module takes what it and its submodules define, not what a module
        sharing its beginning defines (``pkg.cor`` does not take
        ``pkg.core``); ``module:Name`` takes that one constant.
        """
        home = self.home
        if home == source or home.startswith(source + "."):
            return True
        return ":" in source and source == self.key


__all__ = ["Entry", "EntryKind"]
