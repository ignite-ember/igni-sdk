"""A valid value of any type igni-client reads or sends, for a fake's answers.

    from igni_client.models import ProcessTailResult
    from igni_client.testing import sample

    fake.methods.answers["read_process_tail"] = sample(ProcessTailResult)

`sample(T)` fills every field, optional ones included, with a value of its
type: the first of a `Literal`'s values, the first member of a union, one
item in a list or a dict. It is the same value every time, so a test can
compare what came back with it.
"""

from __future__ import annotations

import types
import typing
from datetime import UTC, datetime
from typing import Any, TypeAliasType

from pydantic import BaseModel, JsonValue

#: The time every sampled `datetime` is.
WHEN = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def sample(annotation: Any) -> Any:
    """A valid value of `annotation`: a model, a union, a `Literal`, a container or a scalar."""
    if annotation is JsonValue or annotation is Any:
        return "x"
    if isinstance(annotation, TypeAliasType):
        return sample(annotation.__value__)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        annotation.model_rebuild()
        return annotation.model_validate(
            {
                field.alias or name: _jsonable(sample(field.annotation))
                for name, field in annotation.model_fields.items()
            }
        )
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Annotated:
        return sample(args[0])
    if origin is typing.Literal:
        return args[0]
    if origin in (typing.Union, types.UnionType):
        members = [a for a in args if a is not type(None)]
        return sample(members[0]) if members else None
    if origin is list:
        return [sample(args[0])]
    if origin is dict:
        return {"k": sample(args[1])}
    if origin is tuple:
        return tuple(sample(a) for a in args)
    return _SCALARS[annotation]


_SCALARS: dict[Any, Any] = {
    str: "x",
    int: 1,
    float: 1.5,
    bool: True,
    type(None): None,
    None: None,
    datetime: WHEN,
}


def _jsonable(value: Any) -> Any:
    """A model as the dict it is validated from, so a discriminated union reads it back."""
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True)
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


__all__ = ["WHEN", "sample"]
