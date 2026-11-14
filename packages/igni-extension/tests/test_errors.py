"""What can go wrong: the SDK's errors, their codes and what each says."""

from __future__ import annotations

import pytest

from igni_extension import (
    HostError,
    HostErrorCode,
    HostUnavailable,
    IgniExtensionError,
    NotConfigured,
    NotSignedIn,
)

CODES = {
    "NOT_GRANTED": "not_granted",
    "NOT_FOUND": "not_found",
    "INVALID": "invalid",
    "READ_ONLY": "read_only",
    "STAGE_2": "stage_2",
    "REFUSED": "refused",
    "UNAVAILABLE": "unavailable",
    "FAILED": "failed",
}


def test_the_host_error_codes_are_the_eight_strings_igni_sends() -> None:
    assert {member.name: member.value for member in HostErrorCode} == CODES


@pytest.mark.parametrize("code", sorted(CODES.values()))
def test_a_known_code_is_its_enum_member_and_still_equals_the_string(code: str) -> None:
    error = HostError(code, "a sentence")

    assert error.code is HostErrorCode(code)
    assert isinstance(error.code, HostErrorCode)
    assert error.code == code


def test_a_code_a_newer_igni_sends_stays_the_plain_string() -> None:
    error = HostError("quota_exceeded", "too many")

    assert error.code == "quota_exceeded"
    assert type(error.code) is str


def test_a_code_given_as_a_member_stays_that_member() -> None:
    assert HostError(HostErrorCode.NOT_FOUND, "x").code is HostErrorCode.NOT_FOUND


def test_the_message_is_the_hosts_sentence_everywhere() -> None:
    error = HostError("refused", "Ünïcode — the person could not either")

    assert error.message == str(error) == "Ünïcode — the person could not either"


def test_an_empty_code_and_message_are_kept_as_they_came() -> None:
    error = HostError("", "")

    assert error.code == "" and type(error.code) is str
    assert error.message == "" == str(error)


def test_the_documentation_names_every_code() -> None:
    doc = HostError.__doc__ or ""

    assert all(f"`{code}`" in doc for code in CODES.values())


@pytest.mark.parametrize(
    "raised",
    [
        NotSignedIn(),
        NotConfigured("no service"),
        HostUnavailable("no answer"),
        HostError("failed", "it was tried"),
    ],
)
def test_everything_raised_on_purpose_is_one_family(raised: IgniExtensionError) -> None:
    with pytest.raises(IgniExtensionError):
        raise raised


def test_not_signed_in_tells_the_person_what_to_do_unless_told_otherwise() -> None:
    assert str(NotSignedIn()) == "Sign in to igni to reach this extension's service."
    assert str(NotSignedIn("Open igni first.")) == "Open igni first."


def test_the_errors_are_told_apart() -> None:
    errors = (NotSignedIn, NotConfigured, HostUnavailable, HostError)

    assert not any(issubclass(a, b) for a in errors for b in errors if a is not b), (
        "a handler for one never catches another"
    )
