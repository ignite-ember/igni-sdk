"""Generate igni-client's typed models and methods from igni-core's RPC contract.

igni-core publishes ``docs/rpc-contract.json``; this repository keeps a copy
in ``contracts/rpc-contract.json`` (``make contracts``), and this writes

* ``packages/igni-client/src/igni_client/models.py`` — a Pydantic model for
  every type the contract defines that a client sends or reads, every
  message on igni's socket among them, with the contract's descriptions as
  docstrings;
* ``packages/igni-client/src/igni_client/api.py`` — every method a client
  calls, as a typed Python method on ``IgniClient`` (scope ``igni``) or on
  ``Session`` (scope ``session``), grouped by namespace, with the contract's
  documentation as its docstring; and the table that says, per method, who
  may call it, how igni answers and what it streams;
* the API reference in ``packages/igni-client/README.md``, between its
  ``<!-- api-reference:start -->`` and ``<!-- api-reference:end -->``
  markers — igni-client's PyPI page.

Neither Python file is edited by hand, nor is the README between the
markers. ``tests/test_the_client_api_is_generated.py`` regenerates all three
in memory and fails when what is checked in differs; ``make client-api``
writes them. What a method is called in Python is the one decision made by
hand, in ``tools/client_names.py``; the generator refuses a contract with a
method that table does not place.

The Python is formatted with the repository's ``ruff``, so what is checked in
passes the package's own ``ruff format --check``.

This module writes and checks the files; the parts it composes each have a
module of their own: ``client_plan`` (which methods and defs, and where),
``client_types`` (JSON Schema → annotations), ``client_models``,
``client_api`` and ``client_reference`` (the three outputs), with
``client_signatures`` and ``client_python`` the pieces they share.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools.client_api import ApiGenerator
from tools.client_contract import CONTRACT_FILE, RpcContract
from tools.client_models import ModelsGenerator
from tools.client_names import (
    ACCESS_NOTES,
    HAND_WRITTEN_NAMESPACES,
    MESSAGE_DOCS,
    MESSAGE_METHODS,
    MESSAGES_NOT_SENT,
    OWNER_DOCS,
)
from tools.client_plan import Placement, Plan, class_for_group, hoisted, push_class
from tools.client_python import (
    ContractError,
    Imports,
    docstring,
    field_name,
    pascal,
    snake,
)
from tools.client_reference import README_END, README_START, ReferenceGenerator
from tools.client_types import Types

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = Path("packages/igni-client")
MODELS_OUTPUT = PACKAGE / "src/igni_client/models.py"
API_OUTPUT = PACKAGE / "src/igni_client/api.py"
README = PACKAGE / "README.md"


def ruff_format(text: str, path: Path) -> str:
    """``text`` as the package's ``ruff`` leaves it: imports sorted, then formatted."""
    # igni_client is first-party whether or not the file written here exists yet: ruff finds
    # that out from the disk, and a first run would otherwise sort differently from the next.
    first_party = ["--config", 'lint.isort.known-first-party = ["igni_client"]']
    for command in (["check", "--select", "I", "--fix", "--quiet", *first_party], ["format"]):
        done = subprocess.run(  # noqa: S603 — this interpreter's ruff, on our own output
            [sys.executable, "-m", "ruff", *command, "--stdin-filename", str(path), "-"],
            input=text,
            capture_output=True,
            text=True,
            check=False,
            cwd=path.parent,
        )
        if done.returncode != 0:
            raise ContractError(f"ruff could not format the generated {path.name}: {done.stderr}")
        text = done.stdout
    return text


class ClientApi:
    """The generated files, and whether what is on disk is current."""

    def __init__(self, root: Path = ROOT, contract: RpcContract | None = None) -> None:
        self.root = root
        self.contract = contract or RpcContract.read(root / CONTRACT_FILE.relative_to(ROOT))

    def outputs(self) -> dict[Path, str]:
        plan = Plan(self.contract)
        models = ModelsGenerator(plan).generate()
        api_gen = ApiGenerator(plan)
        api = api_gen.generate()
        reference = ReferenceGenerator(plan, api_gen).generate()
        readme_path = self.root / README
        readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
        return {
            self.root / MODELS_OUTPUT: ruff_format(models, self.root / MODELS_OUTPUT),
            self.root / API_OUTPUT: ruff_format(api, self.root / API_OUTPUT),
            readme_path: self.splice(readme, reference),
        }

    @staticmethod
    def splice(readme: str, reference: str) -> str:
        """``readme`` with its API reference replaced by ``reference``."""
        start, end = readme.find(README_START), readme.find(README_END)
        if start < 0 or end < start:
            raise ContractError(
                f"{README} has no {README_START} … {README_END} section to write the reference into"
            )
        return readme[:start] + reference + readme[end + len(README_END) :]

    def write(self) -> list[Path]:
        """Write every output that differs from what is on disk; return those written."""
        outputs = self.outputs()
        written = self._differing(outputs)
        for path in written:
            path.write_text(outputs[path], encoding="utf-8")
        return written

    def stale(self) -> list[Path]:
        """The outputs whose file on disk is missing or differs from what would be written."""
        return self._differing(self.outputs())

    @staticmethod
    def _differing(outputs: dict[Path, str]) -> list[Path]:
        return [
            path
            for path, text in outputs.items()
            if not path.exists() or path.read_text(encoding="utf-8") != text
        ]


def main() -> int:
    for path in ClientApi().write():
        print("wrote", path.relative_to(ROOT))
    return 0


__all__ = [
    "ACCESS_NOTES",
    "API_OUTPUT",
    "HAND_WRITTEN_NAMESPACES",
    "MESSAGES_NOT_SENT",
    "MESSAGE_DOCS",
    "MESSAGE_METHODS",
    "MODELS_OUTPUT",
    "OWNER_DOCS",
    "README",
    "README_END",
    "README_START",
    "ApiGenerator",
    "ClientApi",
    "ContractError",
    "Imports",
    "ModelsGenerator",
    "Placement",
    "Plan",
    "ReferenceGenerator",
    "Types",
    "class_for_group",
    "docstring",
    "field_name",
    "hoisted",
    "main",
    "pascal",
    "push_class",
    "ruff_format",
    "snake",
]


if __name__ == "__main__":
    raise SystemExit(main())
