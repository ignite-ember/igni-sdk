"""A target's params are JSON on the wire: what JSON cannot hold is refused where it is written."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from igni_service import Target


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_a_target_param_that_json_cannot_hold_is_refused_where_it_is_written(
    number: float,
) -> None:
    with pytest.raises(ValidationError, match="NaN or infinity"):
        Target(page="p", params={"score": number})

    assert Target(page="p", params={"score": 1.5}).params == {"score": 1.5}
