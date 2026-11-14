"""The registration, revocation and discovery models carry their words and their defaults.

Their field docs are attribute docstrings (`use_attribute_docstrings`), so
a model's JSON schema, and the generated pages that read it, say what each
field is. These are the fields that have words, and the wire defaults that
the attribute-docstring move must not have changed.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from igni_service.registration import PublishedExtension
from igni_service.revocations import Revocation, RevocationList
from igni_service.server import Discovery

DESCRIBED: dict[type[BaseModel], list[str]] = {
    PublishedExtension: ["extension_id", "version", "sha256", "held", "reason", "added"],
    Revocation: ["org_id", "subject_id", "incarnation", "not_before_ms", "reason"],
    Discovery: ["issuer", "authorization_endpoint"],
}


@pytest.mark.parametrize(
    ("model", "field"), [(m, f) for m, fields in DESCRIBED.items() for f in fields]
)
def test_a_field_with_an_attribute_docstring_has_it_as_its_description(
    model: type[BaseModel], field: str
) -> None:
    description = model.model_fields[field].description

    assert description and description.strip() == description
    assert model.model_json_schema()["properties"][field]["description"] == description


def test_the_words_say_what_the_fields_are() -> None:
    assert "what its tokens name as `iss`" in (Discovery.model_fields["issuer"].description or "")
    assert "iat_ms" in (Revocation.model_fields["not_before_ms"].description or "")
    assert "SHA-256" in (PublishedExtension.model_fields["sha256"].description or "")


def test_the_wire_defaults_the_move_to_docstrings_left_alone() -> None:
    revocation = Revocation.model_validate({"kind": "app", "subject_id": "a", "not_before_ms": 1})
    assert (revocation.org_id, revocation.incarnation, revocation.reason) == (None, None, "")
    assert Discovery(issuer="x").authorization_endpoint == ""
    assert RevocationList.KEPT_MS == 31 * 86_400_000
