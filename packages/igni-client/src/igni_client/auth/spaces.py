"""An app's spaces: its end users, each one a token source of its own."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from igni_client.auth.tokens import TokenCache
from igni_client.errors import NotAllowed, Unavailable

if TYPE_CHECKING:  # `App` makes its `Spaces`; the import back is for the annotations only
    from igni_client.auth.app import App


class SpaceRecord(BaseModel):
    """One space of an app, as igni server keeps it."""

    model_config = ConfigDict(extra="ignore")

    space_id: str
    app_id: str = ""
    org_id: str = ""
    external_id: str = ""
    created_at: str = ""


class SpacePage(BaseModel):
    """One page of an app's spaces, and the cursor to the next."""

    model_config = ConfigDict(extra="ignore")

    spaces: list[SpaceRecord]
    #: Passed back as `after` for the next page; null on the last.
    next: str | None


class SpaceListQuery(BaseModel):
    """The query of one page of an app's spaces: its size, and where it starts."""

    limit: int
    #: The `next` of the page before; left out for the first page.
    after: str | None = None

    def params(self) -> dict[str, str | int]:
        """The query as the request's parameters, without a cursor it does not have."""
        return self.model_dump(exclude_none=True)


class Spaces:
    """The spaces of one app: declare, look up, list and delete them, and act as one."""

    def __init__(self, app: App) -> None:
        self._app = app

    async def declare(self, external_id: str) -> Space:
        """The space for `external_id` (your own id for the user), made if it is new.

        Idempotent: declaring the same id again returns the same space.
        igni provisions its VM in the background.
        """
        _checked_id(external_id)
        what = "declaring a space"
        response = await self._app.request("PUT", self._path(external_id), what=what)
        return self._space(_parsed(response, SpaceRecord, what=what))

    async def get(self, external_id: str) -> Space | None:
        """The space for `external_id`, or `None` when the app has none."""
        _checked_id(external_id)
        what = "reading a space"
        response = await self._app.request("GET", self._path(external_id), what=what)
        if response.status_code == 404:
            return None
        return self._space(_parsed(response, SpaceRecord, what=what))

    async def list(self, *, limit: int = 100) -> list[SpaceRecord]:
        """Every space of this app."""
        what = "listing spaces"
        found: list[SpaceRecord] = []
        query = SpaceListQuery(limit=limit)
        while True:
            response = await self._app.request(
                "GET", self._path(), what=what, params=query.params()
            )
            page = _parsed(response, SpacePage, what=what)
            found.extend(page.spaces)
            if not page.next:
                return found
            query = SpaceListQuery(limit=limit, after=page.next)

    async def delete(self, external_id: str) -> None:
        """Delete a space: its credential stops working and its VM is erased."""
        _checked_id(external_id)
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
        # Read through the app at each renewal, so a clock or margin set on it later is followed.
        self._tokens = TokenCache(lambda: app.clock(), renew_before=lambda: app.RENEW_BEFORE)

    @property
    def external_id(self) -> str:
        return self.record.external_id if self.record else ""

    async def token(self) -> str:
        """The space's token (`token_use=space`), renewed shortly before it runs out."""
        return await self._tokens.get(lambda: self.app.exchange(self.space_id))


def _checked_id(external_id: str) -> None:
    # An empty id would address the collection: a `DELETE` of it is not a space's.
    if not external_id or "/" in external_id or len(external_id) > 200:
        raise ValueError("a space's external id is 1 to 200 characters, without '/'")


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
