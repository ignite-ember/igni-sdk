"""`ServiceLogs.make_visible`: a handler only when nothing else would show the SDK's lines."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from igni_service.logs import LOGGER, ServiceLogs


@contextmanager
def bare() -> Iterator[logging.Logger]:
    """The root without handlers (pytest adds its own) and `igni_service` untouched."""
    root = logging.getLogger()
    logger = logging.getLogger(LOGGER)
    saved = (root.handlers[:], logger.handlers[:], logger.level)
    root.handlers[:] = []
    logger.handlers[:] = []
    logger.setLevel(logging.NOTSET)
    try:
        yield logger
    finally:
        root.handlers[:] = saved[0]
        logger.handlers[:] = saved[1]
        logger.setLevel(saved[2])


def test_with_no_handler_anywhere_the_lines_become_visible_in_uvicorns_shape(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with bare() as logger:
        assert ServiceLogs.make_visible() is True

        logger.info("igni: uploaded extension acme")
        logger.warning("igni: refused a token")

        assert logger.level == logging.INFO
    assert capsys.readouterr().err.splitlines() == [
        "INFO:     igni: uploaded extension acme",
        "WARNING:  igni: refused a token",
    ]


def test_a_second_call_adds_nothing() -> None:
    with bare() as logger:
        assert ServiceLogs.make_visible() is True
        assert ServiceLogs.make_visible() is False
        assert len(logger.handlers) == 1


def test_a_root_handler_is_left_alone() -> None:
    with bare() as logger:
        logging.getLogger().addHandler(logging.NullHandler())

        assert ServiceLogs.make_visible() is False
        assert logger.handlers == []
        assert logger.level == logging.NOTSET


def test_a_handler_on_igni_service_is_left_alone() -> None:
    with bare() as logger:
        own = logging.NullHandler()
        logger.addHandler(own)

        assert ServiceLogs.make_visible() is False
        assert logger.handlers == [own]


def test_a_level_the_service_chose_is_kept() -> None:
    with bare() as logger:
        logger.setLevel(logging.WARNING)

        assert ServiceLogs.make_visible() is True
        assert logger.level == logging.WARNING


def test_the_level_name_is_changed_for_this_handler_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen: list[str] = []

    class Other(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(record.levelname)

    with bare() as logger:
        ServiceLogs.make_visible()
        logger.addHandler(Other())
        logger.info("hello")

    assert seen == ["INFO"]
    assert "INFO:     hello" in capsys.readouterr().err
