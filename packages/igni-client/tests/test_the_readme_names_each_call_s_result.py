"""Where the README's prose says what a call returns, it is what the reference says.

The Concepts example commented `session.models.switch("igni-1")   # an
InfoMessage`, and "Changes since 0.1.0" said the same, while the method
reference (generated from igni-core's contract) and the call itself give a
`ModelSwitched`.
"""

from __future__ import annotations

import re
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"

#: `<summary><code>await session.models.switch(model_name: str)</code> → <code>ModelSwitched</code>`
_REFERENCE = re.compile(r"<summary><code>await ([\w.]+)\(.*?\)</code> → <code>([^<]+)</code>")
#: `x = await session.models.switch("igni-1")   # an InfoMessage`
_COMMENTED = re.compile(r"await ([\w.]+)\(.*\)\s+# an? (\w+)")
#: `` `session.models.switch(name)` (an `InfoMessage`) ``
_PROSE = re.compile(r"`([\w.]+)\([^`]*\)` \(an? `(\w+)`")


def test_every_result_the_prose_names_is_the_reference_s() -> None:
    text = README.read_text(encoding="utf-8")
    returns = dict(_REFERENCE.findall(text))
    named = _COMMENTED.findall(text) + _PROSE.findall(text)

    assert named, "the README names no call's result"
    wrong = [
        f"{call} said {said}, the reference {returns[call]}"
        for call, said in named
        if call in returns and returns[call] != said
    ]
    assert not wrong, wrong
