"""The host model says what each parameter is, from the schema or from the table.

igni's host schema describes only some of the parameters its methods take;
``tools/host_codegen.py`` carries a table (``PARAM_MEANINGS``) for the rest,
and both generated SDKs document a parameter from one or the other. A
parameter in neither is left undocumented, never given a guessed meaning.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import igni_extension.host_model as host_model

from tools.host_codegen import (
    HOST_SCHEMA,
    PARAM_MEANINGS,
    TYPESCRIPT_OUTPUT,
    ObjectNaming,
    param_meaning,
)
from tools.param_docs import python_args

ROOT = Path(__file__).resolve().parent.parent
ROOT_NAMING = ObjectNaming(HOST_SCHEMA)


def _parameters() -> list[tuple[str, str, str, str]]:
    """Every parameter of every host method: object path, method, name, the schema's words."""
    return [
        (obj.path, method.name, param.name, param.doc.strip())
        for obj in HOST_SCHEMA.objects
        for method in obj.methods
        for param in method.params
    ]


def test_the_schemas_words_win_over_the_table_and_the_table_fills_what_the_schema_leaves() -> None:
    key = next(iter(PARAM_MEANINGS))
    assert param_meaning(*key, doc="The schema's words.") == "The schema's words."
    assert param_meaning(*key, doc="  \n") == PARAM_MEANINGS[key]
    assert param_meaning(*key) == PARAM_MEANINGS[key]
    assert param_meaning("no.such", "method", "param") == ""
    assert param_meaning("no.such", "method", "param", "  Padded.  ") == "Padded."


def test_every_entry_of_the_table_names_a_parameter_the_schema_leaves_undescribed() -> None:
    undescribed = {(path, method, name) for path, method, name, doc in _parameters() if not doc}
    stray = set(PARAM_MEANINGS) - undescribed
    assert not stray, sorted(stray)


def test_the_generated_python_documents_exactly_the_parameters_with_a_meaning() -> None:
    expected = {
        (ROOT_NAMING.class_name(path), method, name)
        for path, method, name, doc in _parameters()
        if param_meaning(path, method, name, doc)
    }
    documented = set()
    for path, method, name, doc in _parameters():
        cls = getattr(host_model, ROOT_NAMING.class_name(path))
        args = python_args(inspect.getdoc(getattr(cls, method)) or "")
        for arg_name, meaning in args.items():
            documented.add((ROOT_NAMING.class_name(path), method, arg_name))
            if arg_name == name:
                assert meaning == " ".join(param_meaning(path, method, name, doc).split())
    assert documented == expected


def test_the_generated_typescript_says_what_each_parameter_with_a_meaning_is() -> None:
    text = (ROOT / TYPESCRIPT_OUTPUT).read_text(encoding="utf-8")
    missing = []
    for path, method, name, doc in _parameters():
        meaning = param_meaning(path, method, name, doc)
        if meaning and f"@param {name} — {meaning.split(chr(10))[0]}" not in text:
            missing.append((path, method, name))
    assert not missing, missing[:10]
