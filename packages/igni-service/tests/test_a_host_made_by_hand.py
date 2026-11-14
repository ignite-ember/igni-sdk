"""A `Host` built without the wires `IgniService` always supplies says so, instead of failing obscurely."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from igni_service import IgniService, Producer
from igni_service.host import Host
from igni_service.testing import FakeIgni
from igni_service.urls import IgniPaths

from .conftest import ORG


def bare_host(igni: IgniService) -> Host:
    return Host(ORG, notifier=igni.outbound.notifier, directory=igni.outbound.directory)


async def test_without_the_vm_profiles_client_the_extension_profile_cannot_be_asked(
    igni: IgniService,
) -> None:
    with pytest.raises(RuntimeError, match="VM profiles"):
        await bare_host(igni).extension_vm_profile()


async def test_the_deprecated_alias_refuses_the_same_way_after_warning(igni: IgniService) -> None:
    with (
        pytest.warns(DeprecationWarning, match="extension_vm_profile"),
        pytest.raises(RuntimeError, match="VM profiles"),
    ):
        await bare_host(igni).vm_profile()


def test_without_the_agents_wire_there_is_no_agent(igni: IgniService) -> None:
    with pytest.raises(RuntimeError, match="agents"):
        bare_host(igni).agent(Producer.person("u-max"))


async def test_send_event_without_the_agents_wire_is_refused_too(igni: IgniService) -> None:
    with pytest.raises(RuntimeError, match="agents"):
        await bare_host(igni).send_event(Producer.person("u-max"), "claim.created")


async def test_send_event_passes_its_expiry_on(igni: IgniService, fake: FakeIgni) -> None:
    expires = datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC)

    await igni.host(ORG).send_event(Producer.person("u-max"), "claim.created", expires_at=expires)

    [seen] = fake.traffic.requests_to(IgniPaths.SERVICE_EVENTS)
    assert seen.json_body()["expires_at"].startswith("2030-01-02T03:04:05")


def test_a_host_for_no_organisation_is_refused(igni: IgniService) -> None:
    with pytest.raises(ValueError, match="one organisation"):
        Host("", notifier=igni.outbound.notifier, directory=igni.outbound.directory)
