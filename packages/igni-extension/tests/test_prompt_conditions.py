"""`ext.prompt.hold`: a manifest's `when`, said by the extension, over a real MCP session."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from igni_extension import IgniExtension
from igni_extension.notifications import ConditionsParams
from igni_extension.testing import HostHarness


async def test_a_condition_crosses_the_wire_as_the_host_reads_it() -> None:
    ext = IgniExtension("acme.example", environ={})

    async with HostHarness(ext) as host:
        await ext.prompt.hold("index-covers-head", True)
        assert await host.conditions_said(1) == [{"index-covers-head": True}]

    assert host.raw == [
        {
            "jsonrpc": "2.0",
            "method": "notifications/igni/conditions",
            "params": {"conditions": {"index-covers-head": True}},
        }
    ]


async def test_saying_the_same_again_sends_nothing() -> None:
    ext = IgniExtension("acme.example", environ={})

    async with HostHarness(ext) as host:
        await ext.prompt.hold("ready", True)
        await ext.prompt.hold("ready", True)
        await ext.prompt.set({"ready": True, "fresh": False})
        assert await host.conditions_said(2) == [{"ready": True}, {"fresh": False}]
    assert ext.prompt.holding == {"ready": True, "fresh": False}


async def test_what_is_said_before_the_host_connects_arrives_when_it_does() -> None:
    """An extension says what holds as it starts, before igni's handshake."""
    ext = IgniExtension("acme.example", environ={})
    await ext.prompt.hold("ready")

    async with HostHarness(ext) as host:
        assert await host.conditions_said(1) == [{"ready": True}]


async def test_refresh_asks_igni_to_fetch_the_text_again() -> None:
    ext = IgniExtension("acme.example", environ={})

    async with HostHarness(ext) as host:
        await ext.prompt.refresh()
        await host.conditions_said(1)

    assert host.raw[-1]["params"] == {"conditions": {}, "refresh": True}


@pytest.mark.parametrize("name", ["Ready", "index covers head", "", "1st"])
def test_a_name_no_manifest_could_use_is_refused_where_it_is_written(name: str) -> None:
    with pytest.raises(ValidationError):
        ConditionsParams(conditions={name: True})


async def test_holding_is_a_copy_and_a_name_can_be_flipped_back_and_is_sent_again() -> None:
    ext = IgniExtension("acme.example", environ={})

    async with HostHarness(ext) as host:
        await ext.prompt.hold("ready", True)
        ext.prompt.holding["ready"] = False  # a copy: this changes nothing
        ext.prompt.holding["other"] = True
        assert ext.prompt.holding == {"ready": True}

        await ext.prompt.hold("ready", False)
        await ext.prompt.hold("ready", True)
        assert await host.conditions_said(3) == [
            {"ready": True},
            {"ready": False},
            {"ready": True},
        ]


async def test_hold_says_a_condition_holds_unless_told_it_does_not() -> None:
    ext = IgniExtension("acme.example", environ={})

    async with HostHarness(ext) as host:
        await ext.prompt.hold("ready")
        await ext.prompt.hold("stale", holds=False)
        assert await host.conditions_said(2) == [{"ready": True}, {"stale": False}]


async def test_saying_nothing_sends_nothing() -> None:
    ext = IgniExtension("acme.example", environ={})

    async with HostHarness(ext) as host:
        await ext.prompt.set({})
        await ext.prompt.hold("ready")
        assert await host.conditions_said(1) == [{"ready": True}]

    assert len(host.raw) == 1


async def test_a_bad_name_leaves_what_was_said_unchanged_and_sends_nothing() -> None:
    ext = IgniExtension("acme.example", environ={})

    async with HostHarness(ext) as host:
        await ext.prompt.hold("ready")
        with pytest.raises(ValidationError):
            await ext.prompt.set({"fresh": True, "Not A Name": True})
        assert ext.prompt.holding == {"ready": True}

        await ext.prompt.hold("fresh")  # it was never recorded, so it is still news
        assert await host.conditions_said(2) == [{"ready": True}, {"fresh": True}]


async def test_a_refresh_is_sent_every_time_and_records_no_condition() -> None:
    ext = IgniExtension("acme.example", environ={})

    async with HostHarness(ext) as host:
        await ext.prompt.refresh()
        await ext.prompt.refresh()
        await host.conditions_said(2)

    assert [message["params"] for message in host.raw] == [{"conditions": {}, "refresh": True}] * 2
    assert ext.prompt.holding == {}
