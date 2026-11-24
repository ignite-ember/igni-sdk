"""The reference shows each igni-client method's TypeScript signature beside its Python one.

igni-client ships in Python and in TypeScript, and the site pairs a
```python block with the ```typescript block right after it into one
toggle. The TypeScript signature is read from ``api.generated.ts`` — what an
npm user gets — by the wire method each generated method calls.

What we pin:

* a one-line method, a method written over several lines, and a followed
  method are read with their whole signature; a constructor is not a method;
* a long signature is laid out one parameter a line, a short one stays on
  one line, and a generic type's commas do not split a parameter;
* a wire method no generated method calls is refused, naming it;
* every method of the real client is found, and each method section of
  the reference carries its TypeScript signature right after the Python one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.client_contract import RpcContract
from tools.client_errors_doc import read_errors
from tools.client_names import MESSAGE_METHODS, METHODS
from tools.client_site import ClientReference
from tools.client_ts import API_OUTPUT
from tools.client_ts_signatures import TsSignatures
from tools.markdown_pages import ReadmePages
from tools.site_page import DocsError

ROOT = Path(__file__).resolve().parent.parent

GENERATED = """\
export class IgniThings {
  constructor(
    readonly caller: Caller,
  ) {}

  /** One line. */
  list(): Promise<Thing[]> {
    return this.caller.rpc<Thing[]>("list_things", {});
  }

  /** Over several lines, in the source. */
  run(
    name: string,
    args?: Record<string, JsonValue>,
  ): Call<RunResult, RunThingEvent> {
    return this.caller.follow<RunResult, RunThingEvent>("run_thing", { name: name, args: args });
  }

  /** A long one. */
  make(first_argument_name: string, second_argument_name?: Map<string, number>, third?: boolean): Promise<void> {
    return this.caller.rpc<void>("make_thing", {});
  }
}
"""


@pytest.fixture
def signatures(tmp_path: Path) -> TsSignatures:
    source = tmp_path / "api.generated.ts"
    source.write_text(GENERATED, encoding="utf-8")
    return TsSignatures.read(source)


def test_a_one_line_method_is_read_whole(signatures: TsSignatures) -> None:
    assert signatures.of("list_things") == "list(): Promise<Thing[]>"


def test_a_method_over_several_lines_is_read_and_fits_on_one(signatures: TsSignatures) -> None:
    assert signatures.of("run_thing") == (
        "run(name: string, args?: Record<string, JsonValue>): Call<RunResult, RunThingEvent>"
    )


def test_a_long_signature_takes_a_line_a_parameter_and_keeps_generics_whole(
    signatures: TsSignatures,
) -> None:
    assert signatures.of("make_thing") == (
        "make(\n"
        "  first_argument_name: string,\n"
        "  second_argument_name?: Map<string, number>,\n"
        "  third?: boolean,\n"
        "): Promise<void>"
    )


def test_a_constructor_is_not_a_method(signatures: TsSignatures) -> None:
    assert all("constructor" not in signatures.of(w) for w in ("list_things", "run_thing"))


def test_a_wire_method_nothing_calls_is_refused(signatures: TsSignatures) -> None:
    with pytest.raises(DocsError, match="no method calling gone_thing"):
        signatures.of("gone_thing")


def test_every_method_of_the_real_client_has_a_typescript_signature() -> None:
    signatures = TsSignatures.read(API_OUTPUT)

    for wire in {*METHODS, *MESSAGE_METHODS}:
        assert signatures.of(wire), wire


@pytest.fixture(scope="module")
def client() -> ClientReference:
    readme = (ROOT / "packages/igni-client/README.md").read_text(encoding="utf-8")
    return ClientReference(
        RpcContract.read(),
        read_errors(ROOT / "packages/igni-client/src/igni_client/errors.py"),
        ReadmePages(readme, "packages/igni-client/README.md"),
    )


def test_each_method_section_pairs_its_python_signature_with_the_typescript_one(
    client: ClientReference,
) -> None:
    signatures = TsSignatures.read(API_OUTPUT)
    for wire in client.sources.layout.placements:
        lines = client.methods.section(wire)
        python = lines.index("```python")
        close = lines.index("```", python + 1)
        assert lines[close + 1 : close + 3] == ["", "```typescript"], wire
        assert lines[close + 3] == signatures.of(wire), wire
