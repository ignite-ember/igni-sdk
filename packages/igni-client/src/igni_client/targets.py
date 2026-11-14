"""Where an igni is: on this machine, or in Fleet behind its gateway.

A target knows how to open igni's socket, and what to do when it closes.
Both speak the same protocol once open — the gateway relays igni's frames
unchanged — so everything above the target is the same code.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import InvalidHandshake, InvalidStatus
from websockets.typing import Subprotocol

from igni_client.access import Standing
from igni_client.auth.tokens import TokenSource
from igni_client.errors import AuthError, NotAllowed, NotSupported, Unavailable

#: The subprotocol igni speaks, locally and through the gateway.
SUBPROTOCOL = Subprotocol("igni.v1")
#: A local igni started by the desktop app wants its per-launch token offered as a subprotocol.
TOKEN_PROTOCOL_PREFIX = "igni-token."  # noqa: S105 — a subprotocol prefix, not a secret
#: Where `Local` finds an approver token when none is passed.
APPROVER_TOKEN_ENV = "IGNI_APPROVER_TOKEN"  # noqa: S105 — an environment variable's name, not a secret
#: igni's frames are at most this large.
MAX_FRAME = 64 * 1024 * 1024
#: Opening may wait on a VM being woken; the gateway holds a client up to 20 s by default.
OPEN_TIMEOUT = 30.0


class Target(Protocol):
    """How to reach one igni."""

    #: Whether a closed socket is worth opening again: Fleet wakes the VM
    #: again, while a local igni that went away has stopped.
    reconnects: bool

    async def open(self) -> ClientConnection: ...

    async def aclose(self) -> None: ...

    def describe(self) -> str: ...

    @property
    def standing(self) -> Standing:
        """What igni lets this connection do, where it is known (`igni_client.access`)."""
        ...


def _refusal(exc: InvalidStatus, where: str) -> Exception:
    status = exc.response.status_code
    body = bytes(exc.response.body or b"").decode(errors="replace").strip()
    detail = body
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            detail = str(parsed.get("error_description") or parsed.get("error") or body)
    except ValueError:
        pass
    if status == 401:
        return AuthError(f"{where} refused the credential: {detail or 'unauthorized'}")
    if status == 403:
        return NotAllowed(f"{where} refused the connection: {detail or 'forbidden'}")
    return Unavailable(f"{where} answered {status}: {detail}")


class Local:
    """An igni running on this machine — the desktop app's, or one started by hand.

    By default it is found from the lockfile a running igni writes in its
    project, `<project_dir>/.igni/backend.lock`, which also carries the
    token a program attaches with when the desktop app launched it. Pass
    `url` (and `token`) to name one directly, such as a backend started with
    `--ws-port 8765`; that one takes no token and checks none.

    A program attached with the lockfile's token runs sessions but cannot
    answer the agent's approval requests: the agent can read the lockfile
    too. To approve, pass `approver_token` (or set `IGNI_APPROVER_TOKEN`),
    a token the person makes in igni's window with `/programs`. igni forgets
    it when it quits.

    Local igni has no gateway, so `commands` and `me()` are not available.
    """

    reconnects = False

    def __init__(
        self,
        project_dir: str | Path = ".",
        *,
        url: str | None = None,
        token: str | None = None,
        approver_token: str | None = None,
    ) -> None:
        self.project_dir = Path(project_dir).expanduser().resolve()
        self._url = url
        self._token = token
        self._approver_token = approver_token or os.environ.get(APPROVER_TOKEN_ENV) or None
        self._standing: Standing = "unknown"

    @property
    def approves(self) -> bool:
        """Whether this connects with an approver token."""
        return self._approver_token is not None

    @property
    def standing(self) -> Standing:
        """What igni stands this connection as (`igni_client.access`).

        An approver with an approver token; with the lockfile's token a
        program; with no token at all igni's window (igni takes none only
        when started without a launch secret). A `token` given by hand may
        be the window's launch secret or the lockfile's, so igni decides.
        Before the lockfile is read, not known.
        """
        if self._approver_token is not None:
            return "approver"
        return self._standing

    def _stand(self, token: str | None, *, given: bool) -> None:
        if token is None:
            self._standing = "window"
        else:
            self._standing = "unknown" if given else "program"

    def _resolve(self) -> tuple[str, str | None]:
        if self._url is not None:
            self._stand(self._token, given=True)
            return self._url, self._approver_token or self._token
        lock = self.project_dir / ".igni" / "backend.lock"
        try:
            payload = json.loads(lock.read_text())
            port = int(payload["port"])
        except FileNotFoundError as exc:
            raise Unavailable(
                f"no igni is running for {self.project_dir} (no {lock}); "
                "open the project in igni, or pass url="
            ) from exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise Unavailable(f"{lock} is not an igni lockfile") from exc
        lockfile_token = payload.get("ws_token") or None
        self._stand(lockfile_token or self._token, given=lockfile_token is None)
        token = self._approver_token or lockfile_token or self._token
        return f"ws://127.0.0.1:{port}", token

    async def open(self) -> ClientConnection:
        url, token = self._resolve()
        protocols = [SUBPROTOCOL]
        if token:
            protocols.append(Subprotocol(f"{TOKEN_PROTOCOL_PREFIX}{token}"))
        try:
            return await connect(
                url,
                subprotocols=protocols,
                max_size=MAX_FRAME,
                compression=None,
                open_timeout=OPEN_TIMEOUT,
            )
        except InvalidStatus as exc:
            if exc.response.status_code == 403:
                # A local igni refuses with 403 for a missing or wrong token
                # (this client sends no Origin, the only other reason).
                if self._approver_token is not None:
                    raise AuthError(
                        f"igni at {url} refused the approver token: it was revoked, or "
                        "igni restarted since it was made; make a new one with /programs"
                    ) from exc
                raise AuthError(
                    f"igni at {url} refused the connection: its token was missing or wrong"
                ) from exc
            raise _refusal(exc, f"igni at {url}") from exc
        except (OSError, InvalidHandshake, TimeoutError) as exc:
            raise Unavailable(f"igni at {url} did not answer: {exc}") from exc

    async def aclose(self) -> None:
        return None

    def describe(self) -> str:
        return f"igni at {self._url or self.project_dir}"


class Fleet:
    """A producer's igni in Fleet, reached through the gateway.

    `url` is the gateway's public address. `auth` decides whose igni it
    is: a `Person`, an `App` or a `Space` — the gateway wakes that
    producer's VM and connects to the igni in it. A fresh token is asked
    of `auth` every time the socket opens.
    """

    reconnects = True

    def __init__(
        self, url: str, *, auth: TokenSource, http: httpx.AsyncClient | None = None
    ) -> None:
        parts = urlsplit(url.rstrip("/"))
        if parts.scheme not in ("http", "https", "ws", "wss"):
            raise ValueError("the gateway's URL is http(s):// or ws(s)://")
        secure = parts.scheme in ("https", "wss")
        self.base = urlunsplit(("https" if secure else "http", parts.netloc, parts.path, "", ""))
        self.connect_url = urlunsplit(
            ("wss" if secure else "ws", parts.netloc, f"{parts.path}/v1/connect", "", "")
        )
        self.auth = auth
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=None))
        self._owns_http = http is None

    async def open(self) -> ClientConnection:
        token = await self.auth.token()
        try:
            return await connect(
                self.connect_url,
                additional_headers={"Authorization": f"Bearer {token}"},
                subprotocols=[SUBPROTOCOL],
                max_size=MAX_FRAME,
                compression=None,
                open_timeout=OPEN_TIMEOUT,
            )
        except InvalidStatus as exc:
            raise _refusal(exc, "the gateway") from exc
        except (OSError, InvalidHandshake, TimeoutError) as exc:
            raise Unavailable(f"the gateway at {self.base} did not answer: {exc}") from exc

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """A call to the gateway's HTTP API, as this producer."""
        headers = {
            "Authorization": f"Bearer {await self.auth.token()}",
            **kwargs.pop("headers", {}),
        }
        try:
            return await self._http.request(method, f"{self.base}{path}", headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise Unavailable(f"the gateway at {self.base} did not answer: {exc}") from exc

    def stream(self, method: str, path: str, token: str, **kwargs: Any) -> Any:
        """A streamed call to the gateway's HTTP API (the caller supplies the token)."""
        headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
        return self._http.stream(method, f"{self.base}{path}", headers=headers, **kwargs)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    def describe(self) -> str:
        return f"igni in Fleet via {self.base}"

    @property
    def standing(self) -> Standing:
        """igni's window: igni on a Fleet VM takes no token and stands every connection so."""
        return "window"


def require_fleet(target: Target, what: str) -> Fleet:
    """`target` as a `Fleet`, or `NotSupported` naming what needed the gateway."""
    if isinstance(target, Fleet):
        return target
    raise NotSupported(f"{what} needs Fleet's gateway; {target.describe()} has none")
