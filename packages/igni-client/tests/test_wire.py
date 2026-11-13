"""What a frame puts on the wire when a value is not JSON."""

from __future__ import annotations

import json
import math

import pytest

from igni_client.models import RpcRequest


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_a_number_json_cannot_hold_is_refused_not_sent_as_invalid_json(value: float) -> None:
    request = RpcRequest(id="1", method="m", args={"a": value})
    with pytest.raises(ValueError, match="not valid JSON"):
        request.wire()


def test_an_ordinary_number_is_sent() -> None:
    sent = json.loads(RpcRequest(id="1", method="m", args={"a": 1.5, "b": 0}).wire())
    assert sent["args"] == {"a": 1.5, "b": 0}
