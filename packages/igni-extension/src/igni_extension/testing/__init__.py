"""igni's side of an extension, played in-process, for the extension's tests.

* `FakeHostTokenEndpoint` — the host's loopback token endpoint
  (`token_endpoint`);
* `FakeHost` — the host's object model on a loopback socket, the way igni
  serves `ext.host` (`fake_host`);
* `HostHarness` — the host's MCP client, connected to the extension over
  memory streams, recording what the extension tells the host
  (`host_harness`);
* `ConcurrencyHarness` — many callers at once (`concurrency`);
* `ManualClock` — a clock a test moves by hand (`clock`).
"""

from __future__ import annotations

from igni_extension.testing.clock import ManualClock
from igni_extension.testing.concurrency import (
    ConcurrencyHarness,
    ConcurrencyProblem,
    ConcurrencyReport,
    ConcurrentCall,
    ConcurrentResult,
)
from igni_extension.testing.fake_host import FakeHost, HostCall
from igni_extension.testing.host_harness import HostHarness
from igni_extension.testing.token_endpoint import FakeHostTokenEndpoint, Minter, TokenClaims

__all__ = [
    "ConcurrencyHarness",
    "ConcurrencyProblem",
    "ConcurrencyReport",
    "ConcurrentCall",
    "ConcurrentResult",
    "FakeHost",
    "FakeHostTokenEndpoint",
    "HostCall",
    "HostHarness",
    "ManualClock",
    "Minter",
    "TokenClaims",
]
