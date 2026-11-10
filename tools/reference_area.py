"""One reference page: its slug, its title, and the names on it.

The Python SDKs' reference (``tools/py_reference.py``) and the npm SDKs'
(``tools/ts_reference.py``) both cut their names into pages, and both
describe a page the same way: a slug the site routes on, a title, the
sources the names come from, and a note under the title saying what the
group is for. This is that description, once.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Area:
    """One reference page: its slug, its title, and the sources on it."""

    slug: str
    title: str
    #: The sources the names come from: a Python module (``igni_service.tokens``)
    #: or a TypeScript file, relative to the package's ``src``.
    sources: tuple[str, ...]
    #: A note under the page's title: what this group of names is for.
    note: str = ""


__all__ = ["Area"]
