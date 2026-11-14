"""The error hierarchy: one root, one `except` for "try later", and refusals that are final."""

from __future__ import annotations

import pytest

from igni_service.errors import (
    BundleError,
    ConfigurationError,
    EventRefused,
    IgniError,
    IgniUnavailable,
    KeyStoreError,
    NotificationRefused,
    ServiceNotApproved,
    ServiceRevoked,
    VmProfileRefused,
)

REFUSALS = [
    (NotificationRefused, "igni refused the notifications: 422 too many"),
    (EventRefused, "igni refused the event: 422 too many"),
    (VmProfileRefused, "igni refused the VM profile request: 422 too many"),
]
EVERY_ERROR = [
    IgniUnavailable,
    ServiceNotApproved,
    ServiceRevoked,
    NotificationRefused,
    EventRefused,
    VmProfileRefused,
    KeyStoreError,
    BundleError,
    ConfigurationError,
]


@pytest.mark.parametrize("error", EVERY_ERROR)
def test_everything_the_sdk_raises_on_purpose_is_an_igni_error(error: type[Exception]) -> None:
    assert issubclass(error, IgniError)


@pytest.mark.parametrize("error", [ServiceNotApproved, ServiceRevoked])
def test_a_service_igni_will_not_answer_is_caught_with_the_unavailable_ones(
    error: type[IgniUnavailable],
) -> None:
    with pytest.raises(IgniUnavailable):
        raise error("not yet")


@pytest.mark.parametrize("error", [ServiceNotApproved, ServiceRevoked])
def test_the_two_kinds_of_unavailable_are_told_apart(error: type[IgniUnavailable]) -> None:
    other = ServiceRevoked if error is ServiceNotApproved else ServiceNotApproved
    assert not issubclass(error, other)


@pytest.mark.parametrize(
    "error", [NotificationRefused, EventRefused, VmProfileRefused, KeyStoreError, BundleError]
)
def test_a_refusal_or_a_local_failure_is_never_a_try_again_later(error: type[Exception]) -> None:
    assert not issubclass(error, IgniUnavailable)
    assert issubclass(error, IgniError)


@pytest.mark.parametrize(("error", "message"), REFUSALS)
def test_a_refusal_carries_igni_s_status_and_words_and_says_both(
    error: type[NotificationRefused], message: str
) -> None:
    refused = error(422, "too many")

    assert refused.status == 422
    assert refused.detail == "too many"
    assert str(refused) == message


@pytest.mark.parametrize(("error", "message"), REFUSALS)
def test_a_refusal_with_no_words_or_unicode_ones_reads_as_given(
    error: type[NotificationRefused], message: str
) -> None:
    assert str(error(403, "")).endswith(": 403 ")
    assert str(error(400, "zu groß — 太多")).endswith(": 400 zu groß — 太多")
