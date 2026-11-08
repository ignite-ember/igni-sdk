"""An app's spaces: its end users, each one a token source of its own."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from igni_client.auth.tokens import TokenCache
from igni_client.errors import NotAllowed, Unavailable

if TYPE_CHECKING:  # `App` makes its `Spaces`; the import back is for the annotations only
    from igni_client.auth.app import App


class SpaceRecord(BaseModel):
    """One space of an app, as igni server keeps it."""

    model_config = ConfigDict(extra="allow")

    space_id: str
    app_id: str = ""
    org_id: str = ""
    external_id: str = ""
    created_at: str = ""


class SpacePage(BaseModel):
    """One page of an app's spaces, and the cursor to the next."""

    model_config = ConfigDict(extra="ignore")

    #: igni server may write an empty page's `spaces` as null; 0.1.0 read any
    #: empty value (null, [], {}, "", 0, false) as none.
    spaces: list[SpaceRecord] | None = None
    #: The cursor is passed back exactly as it came, whatever its JSON type, as in 0.1.0.
    next: Any = None

    @field_validator("spaces", mode="before")
    @classmethod
    def _empty_is_none(cls, value: Any) -> Any:
        return value or None


class Spaces:
    """The spaces of one app: declare, look up, list and delete them, and act as one."""

    def __init__(self, app: App) -> None:
        self._app = app

    async def declare(self, external_id: str) -> Space:
        """The space for `external_id` (your own id for the user), made if it is new.

        Idempotent: declaring the same id again returns the same space.
        igni provisions its VM in the background.
        """
        if not external_id or "/" in external_id or len(external_id) > 200:
            raise ValueError("a space's external id is 1 to 200 characters, without '/'")
        what = "declaring a space"
        response = await self._app.request("PUT", self._path(external_id), what=what)
        return self._space(_parsed(response, SpaceRecord, what=what))

    async def get(self, external_id: str) -> Space | None:
        """The space for `external_id`, or `None` when the app has none."""
        what = "reading a space"
        response = await self._app.request("GET", self._path(external_id), what=what)
        if response.status_code == 404:
            return None
        return self._space(_parsed(response, SpaceRecord, what=what))

    async def list(self, *, limit: int = 100) -> list[SpaceRecord]:
        """Every space of this app."""
        what = "listing spaces"
        found: list[SpaceRecord] = []
        after: Any = None
        while True:
            params: dict[str, Any] = {"limit": limit}
            if after:
                params["after"] = after
            response = await self._app.request("GET", self._path(), what=what, params=params)
            page = _parsed(response, SpacePage, what=what)
            found.extend(page.spaces or [])
            after = page.next
            if not after:
                return found

    async def delete(self, external_id: str) -> None:
        """Delete a space: its credential stops working and its VM is erased."""
        what = "deleting a space"
        response = await self._app.request("DELETE", self._path(external_id), what=what)
        if response.status_code != 404:
            _checked(response, what=what)

    def space(self, space_id: str) -> Space:
        """Act as a space you already know the id of."""
        return Space(self._app, space_id)

    def _space(self, record: SpaceRecord) -> Space:
        return Space(self._app, record.space_id, record=record)

    def _path(self, external_id: str = "") -> str:
        base = f"/v1/apps/{quote(self._app.app_id, safe='')}/spaces"
        return f"{base}/{quote(external_id, safe='')}" if external_id else base


class Space:
    """One space of an app, as a token source: the app's token exchanged for the space's."""

    def __init__(self, app: App, space_id: str, *, record: SpaceRecord | None = None) -> None:
        if not space_id:
            raise ValueError("a space needs its space id")
        self.app = app
        self.space_id = space_id
        self.record = record
        self._tokens = TokenCache(app.clock, renew_before=lambda: app.RENEW_BEFORE)

    @property
    def external_id(self) -> str:
        return self.record.external_id if self.record else ""

    async def token(self) -> str:
        """The space's token (`token_use=space`), renewed shortly before it runs out."""
        return await self._tokens.get(lambda: self.app.exchange(self.space_id))


def _checked(response: httpx.Response, *, what: str) -> None:
    if response.status_code in (400, 403, 409):
        raise NotAllowed(f"igni server refused {what}: {response.text}")
    if response.status_code >= 300:
        raise Unavailable(f"igni server answered {what} with {response.status_code}")


def _parsed[Body: BaseModel](response: httpx.Response, model: type[Body], *, what: str) -> Body:
    _checked(response, what=what)
    try:
        return model.model_validate_json(response.content)
    except ValidationError as exc:
        raise Unavailable(f"igni server answered {what} with something else") from exc
