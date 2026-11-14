"""The generated models, held to igni's contract class by class.

`models.py` is written by the generator, so what is pinned here is what the
generated types do for a user: what they require, what they fill in, what
they refuse, what they keep, and what a client sends.
"""

from __future__ import annotations

import inspect
import json
import typing
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from igni_client import models
from igni_client.api import NOT_FOR_CLIENTS
from igni_client.models import (
    EVENT_TYPES,
    FRAME_TYPES,
    PUSH_TYPES,
    ChatTurn,
    CommandAction,
    CommandResultKind,
    ExtensionIndicator,
    NotificationOrigin,
    PermissionMode,
    PlanDecision,
    PushNotification,
    RpcErrorCode,
    RpcRequest,
    ScheduledTask,
    SlashCommand,
    TaskStatus,
    TodoItem,
    VisualizationDeltaPayload,
    WindowItem,
    WindowModelResult,
    WorkflowListItem,
)
from igni_client.testing import sample
from igni_client.wire import Args, Event, Frame, Model

CONTRACT_FILE = Path(__file__).resolve().parents[3] / "contracts" / "rpc-contract.json"
CONTRACT: dict[str, Any] = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
DEFS: dict[str, Any] = CONTRACT["defs"]


def _classes(base: type) -> list[type]:
    return sorted(
        (
            c
            for _, c in inspect.getmembers(models, inspect.isclass)
            if issubclass(c, base) and c.__module__ == models.__name__
        ),
        key=lambda c: c.__name__,
    )


PUSHES = set(PUSH_TYPES.values())


def _def_of_each_class() -> dict[type[BaseModel], str]:
    """Each class with the contract def it was generated from.

    A class has its def's name, spelt as Python spells it (`McpPrompt` for
    `MCPPrompt`), or is the class of a message or a push channel, which the
    contract names by the def it points at.
    """
    spelt = {name.lower(): name for name in DEFS} | {"todoitem": "TodoItemWire"}
    mapped: dict[type[BaseModel], str] = {}
    for cls in _classes(BaseModel):
        if cls.__name__.lower() in spelt and cls not in PUSHES:
            mapped[cls] = spelt[cls.__name__.lower()]
    for wire_type, cls in {**EVENT_TYPES, **FRAME_TYPES}.items():
        mapped[cls] = CONTRACT["messages"][wire_type]["schema"]["$ref"].rsplit("/", 1)[-1]
    for channel, push in PUSH_TYPES.items():
        ref = CONTRACT["push_channels"][channel]["schema"]["$ref"].rsplit("/", 1)[-1]
        mapped[push.model_fields["payload"].annotation] = ref  # type: ignore[index]
    return mapped


DEF_OF = _def_of_each_class()
MODELS = sorted(DEF_OF, key=lambda c: c.__name__)
ARGS = _classes(Args)
FRAMES = _classes(Frame)
EVENTS = _classes(Event)
KEPT = [c for c in _classes(Model) if c in DEF_OF]


def _default(field: Any) -> Any:
    value = field.default_factory() if field.default_factory else field.default
    return value.model_dump(by_alias=True, mode="json") if isinstance(value, BaseModel) else value


def _reached(node: Any, seen: set[str]) -> None:
    """Every def `node` points at, and the defs those point at."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.rsplit("/", 1)[-1] not in seen:
            seen.add(ref.rsplit("/", 1)[-1])
            _reached(DEFS[ref.rsplit("/", 1)[-1]], seen)
        for value in node.values():
            _reached(value, seen)
    elif isinstance(node, list):
        for value in node:
            _reached(value, seen)


def test_every_def_a_method_message_or_push_reaches_has_its_class() -> None:
    reached: set[str] = set()
    _reached(CONTRACT["messages"], reached)
    _reached(CONTRACT["push_channels"], reached)
    _reached({n: m for n, m in CONTRACT["methods"].items() if n not in NOT_FOR_CLIENTS}, reached)
    literals = {name for name in DEFS if "enum" in DEFS[name]}
    aliases = {n for n in dir(models) if n in literals}
    assert set(DEF_OF.values()) <= set(DEFS)
    missing = reached - set(DEF_OF.values()) - aliases - {"JsonValue"}
    assert not missing, missing
    # What a class is not generated for is a def nothing reaches.
    assert set(DEFS) - set(DEF_OF.values()) - aliases - {"JsonValue"} <= set(DEFS) - reached


def test_every_class_but_the_pushes_comes_from_a_def() -> None:
    assert set(_classes(BaseModel)) - set(DEF_OF) == PUSHES
    assert len(_classes(BaseModel)) == 269


@pytest.mark.parametrize("cls", MODELS, ids=lambda c: c.__name__)
def test_a_class_requires_and_defaults_what_the_contract_says(cls: type[BaseModel]) -> None:
    contract = DEFS[DEF_OF[cls]]
    fields = {f.alias or n: f for n, f in cls.model_fields.items()}
    assert set(fields) == set(contract.get("properties", {}))
    for wire_name, field in fields.items():
        prop = contract["properties"][wire_name]
        assert field.is_required() == (wire_name in contract.get("required", [])), wire_name
        if "default" in prop:
            assert _default(field) == prop["default"], wire_name
        else:
            assert field.is_required() or _default(field) in (None, [], {}), wire_name
        assert field.description == prop.get("description"), wire_name


@pytest.mark.parametrize("cls", MODELS, ids=lambda c: c.__name__)
def test_a_class_s_missing_required_field_is_refused(cls: type[BaseModel]) -> None:
    full = sample(cls).model_dump(by_alias=True, mode="json")
    assert cls.model_validate(full)
    for name, field in cls.model_fields.items():
        if not field.is_required():
            continue
        short = {k: v for k, v in full.items() if k != (field.alias or name)}
        with pytest.raises(ValidationError) as refused:
            cls.model_validate(short)
        assert [e["type"] for e in refused.value.errors()] == ["missing"], name


@pytest.mark.parametrize("cls", ARGS, ids=lambda c: c.__name__)
def test_a_misspelt_argument_is_refused_before_it_is_sent(cls: type[Args]) -> None:
    good = sample(cls).model_dump(by_alias=True, mode="json")
    assert cls.model_validate(good)
    with pytest.raises(ValidationError) as refused:
        cls.model_validate({**good, "definitely_not_an_argument": 1})
    assert [e["type"] for e in refused.value.errors()] == ["extra_forbidden"]


@pytest.mark.parametrize("cls", KEPT, ids=lambda c: c.__name__)
def test_a_field_a_newer_igni_adds_is_kept(cls: type[Model]) -> None:
    full = sample(cls).model_dump(by_alias=True, mode="json")
    read = cls.model_validate({**full, "added_by_a_newer_igni": {"a": [1]}})
    assert read.model_extra == {"added_by_a_newer_igni": {"a": [1]}}


@pytest.mark.parametrize("cls", FRAMES, ids=lambda c: c.__name__)
def test_a_frame_is_frozen_and_refuses_unknown_fields(cls: type[Frame]) -> None:
    frame = cls.model_validate({})
    with pytest.raises(ValidationError) as frozen:
        frame.session_id = "other"
    assert frozen.value.errors()[0]["type"] == "frozen_instance"
    with pytest.raises(ValidationError) as unknown:
        cls.model_validate({"surprise": 1})
    assert unknown.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize("cls", FRAMES, ids=lambda c: c.__name__)
def test_a_frame_sends_its_type_and_only_what_was_set(cls: type[Frame]) -> None:
    wire_type = cls.model_fields["type"].default
    assert json.loads(cls.model_validate({}).wire()) == {"type": wire_type}
    assert json.loads(cls.model_validate({"id": "r-1"}).wire()) == {"type": wire_type, "id": "r-1"}


def test_a_value_json_cannot_hold_is_not_sent() -> None:
    for value in [{1, 2}, b"bytes", object()]:
        with pytest.raises(ValidationError):
            RpcRequest(id="1", method="m", args={"a": value})  # type: ignore[dict-item]


def test_unicode_and_large_text_pass_through_a_frame_unchanged() -> None:
    text = "héllo ☃ \U0001f600 " + "x" * 1_000_000
    sent = json.loads(RpcRequest(id="1", method="m", args={"t": text}).wire())
    assert sent["args"]["t"] == text


@pytest.mark.parametrize(("wire_type", "cls"), sorted({**EVENT_TYPES, **FRAME_TYPES}.items()))
def test_a_message_class_carries_its_wire_type(wire_type: str, cls: type[BaseModel]) -> None:
    assert cls.model_fields["type"].default == wire_type
    if issubclass(cls, Event):
        assert EVENT_TYPES[wire_type] is cls or FRAME_TYPES[wire_type] is cls


def test_every_push_channel_the_contract_types_has_its_class() -> None:
    assert set(PUSH_TYPES) == set(CONTRACT["push_channels"])
    for channel, cls in PUSH_TYPES.items():
        assert issubclass(cls, PushNotification)
        assert cls.model_fields["channel"].default == channel
        payload_def = CONTRACT["push_channels"][channel]["schema"]["$ref"].rsplit("/", 1)[-1]
        payload: Any = cls.model_fields["payload"].annotation
        assert payload in DEF_OF and DEF_OF[payload] == payload_def
        pushed = sample(cls).model_dump(by_alias=True, mode="json")
        read = PUSH_TYPES[channel].model_validate(pushed)
        assert type(read.payload) is payload
        with pytest.raises(ValidationError):
            cls.model_validate({**pushed, "channel": "some_other_channel"})


@pytest.mark.parametrize(
    ("alias", "alias_name", "python_name", "value"),
    [
        (ExtensionIndicator, "intervalSeconds", "interval_seconds", 5.0),
        (VisualizationDeltaPayload, "json", "json_", '{"a": 1}'),
        (TodoItem, "activeForm", "active_form", "Running tests"),
        (WorkflowListItem, "whenToUse", "when_to_use", "when asked"),
    ],
)
def test_an_aliased_field_is_read_by_either_name_and_written_by_the_wire_name(
    alias: type[BaseModel], alias_name: str, python_name: str, value: Any
) -> None:
    base = sample(alias).model_dump(by_alias=True, mode="json")
    base.pop(alias_name)
    by_wire = alias.model_validate({**base, alias_name: value})
    by_python = alias.model_validate({**base, python_name: value})
    assert getattr(by_wire, python_name) == getattr(by_python, python_name) == value
    for read in (by_wire, by_python):
        dumped = read.model_dump(mode="json")
        assert dumped[alias_name] == value
        assert python_name not in dumped


@pytest.mark.parametrize(
    ("alias", "default"),
    [
        (TaskStatus, "pending"),
        (CommandAction, ""),
        (CommandResultKind, "markdown"),
        (NotificationOrigin, "server"),
        (PermissionMode, "default"),
        (PlanDecision, "approved"),
        (RpcErrorCode, "failed"),
    ],
)
def test_a_literal_accepts_the_contract_s_words_and_no_other(alias: Any, default: str) -> None:
    contract = DEFS[alias.__name__]["enum"]
    adapter = TypeAdapter(alias)
    assert set(typing.get_args(alias.__value__)) == set(contract)
    for word in contract:
        assert adapter.validate_python(word) == word
    assert default in contract
    for other in ("not-a-word", "PENDING", " pending", None, 1):
        with pytest.raises(ValidationError):
            adapter.validate_python(other)


def test_a_scheduled_task_needs_its_time_and_fills_the_rest() -> None:
    task = ScheduledTask.model_validate(
        {"id": "a1b2c3d4", "description": "d", "scheduled_at": "2026-01-02T03:04:05Z"}
    )
    assert (task.status, task.error, task.recurrence, task.result) == ("pending", "", "", "")
    assert task.scheduled_at == datetime.fromisoformat("2026-01-02T03:04:05+00:00")
    with pytest.raises(ValidationError):
        ScheduledTask(id="a1b2c3d4", description="d")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ScheduledTask.model_validate(
            {"id": "a", "description": "d", "scheduled_at": "next tuesday"}
        )
    with pytest.raises(ValidationError):
        ScheduledTask(id="a1b2c3d4", description="d", scheduled_at=None)  # type: ignore[arg-type]
    naive = ScheduledTask.model_validate(
        {"id": "a", "description": "d", "scheduled_at": "2026-01-02T03:04:05"}
    )
    assert naive.scheduled_at.tzinfo is None


def test_a_card_update_is_final_unless_said_otherwise_and_an_indicator_polls_every_30_seconds() -> (
    None
):
    assert VisualizationDeltaPayload().final is True
    assert VisualizationDeltaPayload(final=False).final is False
    indicator = ExtensionIndicator(id="a.b", label="l", source="s")
    assert indicator.interval_seconds == 30.0 and indicator.opens == ""


def test_a_required_text_is_not_null_and_a_number_is_not_text() -> None:
    with pytest.raises(ValidationError):
        ExtensionIndicator.model_validate({"id": None, "label": "l", "source": "s"})
    with pytest.raises(ValidationError):
        ExtensionIndicator.model_validate({"id": 5, "label": "l", "source": "s"})
    with pytest.raises(ValidationError):
        ExtensionIndicator.model_validate(
            {"id": "a", "label": "l", "source": "s", "intervalSeconds": "often"}
        )


def test_an_empty_collection_default_is_not_shared_between_instances() -> None:
    shared = 0
    for cls in MODELS:
        for name, field in cls.model_fields.items():
            if field.default_factory is None:
                continue
            first, second = _default(field), _default(field)
            assert first == second and first is not second, (cls.__name__, name)
            shared += 1
    assert shared > 20


@pytest.mark.parametrize(
    ("union", "tag", "kinds"),
    [
        (ChatTurn, "role", 7),
        (SlashCommand, "source", 4),
        (WindowItem, "type", 2),
        (WindowModelResult, "op", 6),
    ],
)
def test_a_union_picks_the_class_its_discriminator_names(union: Any, tag: str, kinds: int) -> None:
    adapter = TypeAdapter(union)
    members = {
        typing.get_args(cls.model_fields[tag].annotation)[0]: cls
        for cls in typing.get_args(typing.get_args(union.__value__)[0])
    }
    assert len(members) == kinds
    for key, cls in members.items():
        assert cls.model_fields[tag].default == key
        value = sample(cls).model_dump(by_alias=True, mode="json")
        assert type(adapter.validate_python(value)) is cls
        without = {k: v for k, v in value.items() if k != tag}
        with pytest.raises(ValidationError) as missing:
            adapter.validate_python(without)
        assert missing.value.errors()[0]["type"] == "union_tag_not_found"
        with pytest.raises(ValidationError) as unknown:
            adapter.validate_python({**value, tag: "no-such-kind"})
        assert unknown.value.errors()[0]["type"] == "union_tag_invalid"
