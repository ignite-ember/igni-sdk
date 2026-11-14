"""Which of igni's methods a connection reaches, by how it attached.

igni-core's contract says, per method, who may call it (`access`):

* `client` — any connection attached to igni;
* `approver` — igni's window, or a program holding an approver token the
  window minted;
* `window` — igni's own window only;
* `page`, `platform` — an extension's page, Fleet's control connection.
  igni-client generates no method for these.

A connection's standing is decided when it attaches, by the token it
offers — igni-core's contract says how (its ``access`` section, quoted in
the README). igni-client refuses a call the connection cannot make before
sending it, with `AccessRefused` — the error igni would answer — wherever
it knows the standing; where it does not, it sends the call and igni
decides, and a refusal comes back as the same `AccessRefused`.

* `Fleet(...)`: the gateway authenticates the client, and igni on the VM
  stands every connection as its window: `client`, `approver` and `window`.
* `Local(project_dir)` attaches with the token in igni's lockfile — a
  program's: `client` only. When the lockfile has no token, igni was started
  with the development opt-out (`IGNI_DEV_NO_WS_TOKEN=1`) and every
  connection is its window.
* `Local(..., approver_token=...)` (or `IGNI_APPROVER_TOKEN`) is an
  approver: `client` and `approver`.
* `Local(url=...)` with no token reaches an igni started with
  `IGNI_DEV_NO_WS_TOKEN=1`: its window; any other igni refuses it. With a
  `token`, it offers whatever it was given — the window's token (the
  launch secret, or the one a backend started by hand prints once to
  stderr), or the lockfile's — so it is not known.
"""

from __future__ import annotations

from typing import Literal

from igni_client.errors import AccessRefused

Access = Literal["client", "approver", "window"]
Standing = Literal["program", "approver", "window", "unknown"]

#: What each standing reaches. An unknown standing is checked by igni.
REACHES: dict[Standing, frozenset[Access] | None] = {
    "program": frozenset({"client"}),
    "approver": frozenset({"client", "approver"}),
    "window": frozenset({"client", "approver", "window"}),
    "unknown": None,
}

_WHY: dict[str, str] = {
    "approver": (
        "only igni's window, or a program holding an approver token the window minted, "
        "may do this (Local(approver_token=...))"
    ),
    "window": "only igni's window may do this",
}


def check(method: str, access: str, standing: Standing) -> None:
    """Raise `AccessRefused` when a connection of `standing` cannot call `method`."""
    reached = REACHES[standing]
    if reached is None or access in reached:
        return
    raise AccessRefused(method, _WHY.get(access, f"a {access} call"))


__all__ = ["REACHES", "Access", "Standing", "check"]
