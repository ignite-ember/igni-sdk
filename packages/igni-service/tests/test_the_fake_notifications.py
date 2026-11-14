"""The fake's notification endpoint: igni's limits, refusals and rules for whom it tells.

Driven at the endpoint with the batches a service posts, so a refusal the
SDK's own splitting would never provoke is seen, and so are the rules for
who is told: active members only, never the actor, an `event_key` once
per person and source.
"""

from __future__ import annotations

import json

import httpx

from igni_service.directory import Member
from igni_service.notifications import Notification, Notifier
from igni_service.testing_bearers import TokenHolder
from igni_service.testing_bundles import HeldExtension, UploadedManifest
from igni_service.testing_clients import FakeClientRegistry
from igni_service.testing_directory import FakeDirectory
from igni_service.testing_extensions import FakeExtensionStore
from igni_service.testing_notifications import DeliveryKey, FakeNotifications
from igni_service.testing_wire import RoutedCall, SeenRequest
from igni_service.urls import IgniPaths

ORG = "org-acme"


class Scene:
    def __init__(self) -> None:
        self.directory = FakeDirectory()
        for user_id, email, status in (
            ("u-ada", "ada@acme.test", "active"),
            ("u-max", "max@acme.test", "active"),
            ("u-sam", "sam@acme.test", "active"),
            ("u-gone", "gone@acme.test", "deactivated"),
        ):
            self.directory.add_member(ORG, Member(user_id=user_id, email=email, status=status))
        self.extensions = FakeExtensionStore(FakeClientRegistry())
        self.fake = FakeNotifications(directory=self.directory, extensions=self.extensions)

    def ship(self, *pages: str, extension_id: str = "tickets") -> None:
        self.extensions.extensions["c-1"] = HeldExtension(
            client_id="c-1",
            extension_id=extension_id,
            version="1.0.0",
            sha256="0" * 64,
            archive=b"",
            manifest=UploadedManifest.model_validate(
                {"contributes": {"pages": [{"kind": page} for page in pages]}}
            ),
        )

    def send(self, *notifications: dict[str, object], org: str = ORG) -> httpx.Response:
        return self.post(json.dumps({"notifications": list(notifications)}).encode(), org=org)

    def post(self, body: bytes, *, org: str = ORG) -> httpx.Response:
        call = RoutedCall(
            seen=SeenRequest(method="POST", path=IgniPaths.NOTIFICATIONS, headers={}, body=body),
            holder=TokenHolder(client_id="c-1", org_id=org),
        )
        return self.fake.notify(call)

    def told(self) -> list[tuple[str, str]]:
        return [(d.user_id, d.notification.title) for d in self.fake.deliveries]


def note(*recipients: str, title: str = "T", **fields: object) -> dict[str, object]:
    return {"kind": "comment", "title": title, "recipients": list(recipients), **fields}


def test_each_active_recipient_is_told_and_the_count_is_answered() -> None:
    scene = Scene()

    answer = scene.send(note("u-max", "sam@ACME.test"))

    assert (answer.status_code, answer.json()) == (200, {"delivered": 2})
    assert scene.told() == [("u-max", "T"), ("u-sam", "T")]
    delivery = scene.fake.deliveries[0]
    assert (delivery.org_id, delivery.source) == (ORG, "")
    assert delivery.notification.kind == "comment"


def test_a_call_is_kept_as_sent() -> None:
    scene = Scene()

    scene.send(note("u-max", title="One"), note("u-sam", title="Two"))

    (call,) = scene.fake.calls
    assert (call.org_id, call.client_id) == (ORG, "c-1")
    assert [n.title for n in call.notifications] == ["One", "Two"]
    assert all(isinstance(n, Notification) for n in call.notifications)


def test_unknown_and_former_recipients_are_skipped_without_an_error() -> None:
    scene = Scene()

    answer = scene.send(note("u-max", "u-gone", "gone@acme.test", "nobody", "u-sam"))

    assert answer.json() == {"delivered": 2}
    assert [user for user, _ in scene.told()] == ["u-max", "u-sam"]


def test_a_recipient_of_another_organisation_is_not_told() -> None:
    scene = Scene()

    answer = scene.send(note("u-max"), org="org-other")

    assert answer.json() == {"delivered": 0}
    assert scene.fake.deliveries == []


def test_the_actor_is_never_told_by_id_or_by_address_in_any_case() -> None:
    scene = Scene()

    by_id = scene.send(note("u-ada", "u-max", actor="u-ada"))
    by_address = scene.send(note("u-ada", "u-sam", actor="ADA@acme.test", title="B"))

    assert by_id.json() == by_address.json() == {"delivered": 1}
    assert scene.told() == [("u-max", "T"), ("u-sam", "B")]


def test_an_actor_the_directory_does_not_know_excludes_nobody() -> None:
    scene = Scene()

    answer = scene.send(note("u-ada", actor="stranger"))

    assert answer.json() == {"delivered": 1}


def test_a_recipient_named_twice_by_id_and_address_is_told_twice_without_a_key() -> None:
    scene = Scene()

    answer = scene.send(note("u-max", "max@acme.test"))

    assert answer.json() == {"delivered": 2}


def test_without_a_key_a_notification_is_told_every_time_it_is_sent() -> None:
    scene = Scene()

    scene.send(note("u-max"))
    scene.send(note("u-max"))

    assert len(scene.fake.deliveries) == 2
    assert scene.fake.told == set()


def test_a_key_tells_each_person_once_however_often_it_is_sent() -> None:
    scene = Scene()

    first = scene.send(note("u-max", "max@acme.test", event_key="k"))
    again = scene.send(note("u-max", "u-sam", event_key="k"))

    assert (first.json(), again.json()) == ({"delivered": 1}, {"delivered": 1})
    assert scene.told() == [("u-max", "T"), ("u-sam", "T")]
    assert scene.fake.told == {
        DeliveryKey(user_id="u-max", source="", event_key="k"),
        DeliveryKey(user_id="u-sam", source="", event_key="k"),
    }


def test_a_key_is_told_again_for_another_key_and_for_another_source() -> None:
    scene = Scene()
    scene.send(note("u-max", event_key="k"))

    other_key = scene.send(note("u-max", event_key="k2"))
    scene.ship()
    other_source = scene.send(note("u-max", event_key="k"))
    same_source = scene.send(note("u-max", event_key="k"))

    assert other_key.json() == {"delivered": 1}
    assert other_source.json() == {"delivered": 1}
    assert same_source.json() == {"delivered": 0}
    assert [d.source for d in scene.fake.deliveries] == ["", "", "tickets"]


def test_a_skipped_recipient_does_not_use_up_the_key_for_the_actor_or_the_former_member() -> None:
    scene = Scene()
    scene.send(note("u-ada", "u-gone", actor="u-ada", event_key="k"))

    assert scene.fake.told == set()
    assert scene.send(note("u-ada", event_key="k")).json() == {"delivered": 1}


def test_the_source_is_the_shipped_extensions_id_and_empty_when_none_shipped() -> None:
    scene = Scene()
    scene.send(note("u-max"))
    scene.ship("tickets", extension_id="tickets")
    scene.send(note("u-max"))

    assert [d.source for d in scene.fake.deliveries] == ["", "tickets"]


def test_a_held_extension_does_not_make_its_pages_known() -> None:
    scene = Scene()
    scene.ship("home")
    scene.extensions.held["c-1"] = scene.extensions.extensions["c-1"].model_copy(
        update={
            "manifest": UploadedManifest.model_validate(
                {"contributes": {"pages": [{"kind": "queue"}]}}
            )
        }
    )

    held_page = scene.send(note("u-max", target={"page": "queue"}))
    shipped_page = scene.send(note("u-max", target={"page": "home"}))

    assert held_page.status_code == 400
    assert shipped_page.status_code == 200


def test_a_target_page_the_shipped_extension_lacks_is_refused_naming_page_and_extension() -> None:
    scene = Scene()
    scene.ship("home", "queue")

    refused = scene.send(note("u-max", target={"page": "billing"}))
    accepted = scene.send(note("u-max", target={"page": "queue", "params": {"id": 3}}))
    untargeted = scene.send(note("u-max"))

    assert refused.status_code == 400
    assert refused.json() == {"detail": "billing is not one of tickets's pages"}
    assert accepted.status_code == untargeted.status_code == 200
    assert len(scene.fake.calls) == 2


def test_without_a_shipped_extension_no_target_page_is_checked() -> None:
    scene = Scene()

    answer = scene.send(note("u-max", target={"page": "anything"}))

    assert answer.json() == {"delivered": 1}


def test_the_limit_of_notifications_in_a_call_is_accepted_and_one_more_is_refused() -> None:
    scene = Scene()

    at_limit = scene.send(*[note("u-max", title=str(i)) for i in range(Notifier.MAX_BATCH)])
    scene.fake.reset()
    over = scene.send(*[note("u-max") for _ in range(Notifier.MAX_BATCH + 1)])

    assert at_limit.json() == {"delivered": Notifier.MAX_BATCH}
    assert (over.status_code, over.json()) == (
        413,
        {"detail": "too many notifications in one call"},
    )
    assert (scene.fake.calls, scene.fake.deliveries) == ([], [])


def test_the_limit_of_recipients_is_accepted_and_one_more_is_refused() -> None:
    scene = Scene()
    names = [f"nobody-{i}" for i in range(Notifier.MAX_RECIPIENTS + 1)]

    at_limit = scene.send(note(*names[:-1]))
    over = scene.send(note(*names))

    assert at_limit.status_code == 200
    assert (over.status_code, over.json()) == (
        413,
        {"detail": "too many recipients in one notification"},
    )
    assert len(scene.fake.calls) == 1


def test_a_refused_call_tells_nobody_and_records_nothing() -> None:
    scene = Scene()
    scene.ship("home")

    scene.send(note("u-max"), note("u-sam", target={"page": "billing"}))

    assert (scene.fake.calls, scene.fake.deliveries, scene.fake.told) == ([], [], set())


def test_no_notifications_is_delivered_zero_and_still_recorded() -> None:
    scene = Scene()

    answer = scene.send()

    assert answer.json() == {"delivered": 0}
    assert len(scene.fake.calls) == 1


def test_a_body_that_is_not_a_batch_is_refused_with_422_and_recorded_nowhere() -> None:
    scene = Scene()

    for body in (b"nonsense", b"{}", b'{"notifications": [{"kind": "x"}]}'):
        answer = scene.post(body)
        assert answer.status_code == 422
        assert answer.json()["detail"]
    assert scene.fake.calls == []


def test_a_reset_empties_the_calls_the_deliveries_and_the_once_only_memory() -> None:
    scene = Scene()
    scene.send(note("u-max", event_key="k"))

    scene.fake.reset()

    assert (scene.fake.calls, scene.fake.deliveries, scene.fake.told) == ([], [], set())
    assert scene.send(note("u-max", event_key="k")).json() == {"delivered": 1}
