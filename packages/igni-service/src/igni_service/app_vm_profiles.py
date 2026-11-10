"""`AppVmProfiles`: an app's VM profile — what it asks for, what became of that, what the VM gets.

`app.vm_profile` on an `igni_service.app.IgniApp`. Every call goes out
with the app's own token; nothing here can approve a request (that is an
org admin's, on the portal).
"""

from __future__ import annotations

from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError

from igni_service.errors import IgniUnavailable
from igni_service.urls import IgniPaths
from igni_service.vm_profiles import (
    AppVmProfile,
    VmProfileRequest,
    VmProfileRequestRecord,
    refusal,
)


class AppCaller(Protocol):
    """Whatever calls igni as one app: `IgniApp.request`."""

    async def request(
        self, method: str, path: str, *, json: object | None = None
    ) -> httpx.Response: ...


class AppVmProfiles:
    """`PUT`/`GET /v1/apps/{app_id}/vm-profile-request` and `GET …/vm-profile`, as the app."""

    def __init__(self, app_id: str, caller: AppCaller) -> None:
        self._app_id = app_id
        self._caller = caller

    async def request(self, wanted: VmProfileRequest) -> VmProfileRequestRecord:
        """Ask for what this app's VM needs. It runs nothing until an org admin approves.

        The same request again changes nothing and keeps its state; a
        changed one is `pending` again, and the VM keeps the profile it has
        until the admin approves the new one. Raises `VmProfileRefused`
        (over the platform's caps, malformed) or `IgniUnavailable`.
        """
        response = await self._caller.request(
            "PUT", IgniPaths.app_vm_profile_request(self._app_id), json=wanted.body()
        )
        if response.status_code in (200, 201):
            return self._parsed(response, VmProfileRequestRecord)
        raise self._failed(response)

    async def status(self) -> VmProfileRequestRecord | None:
        """This app's request and what became of it (`state`, `reason`); `None` if it never asked."""
        response = await self._caller.request("GET", IgniPaths.app_vm_profile_request(self._app_id))
        if response.status_code == 404:
            return None
        if response.status_code == 200:
            return self._parsed(response, VmProfileRequestRecord)
        raise self._failed(response)

    async def effective(self) -> AppVmProfile:
        """The profile this app's VM gets now — approved, or the organisation's default."""
        response = await self._caller.request("GET", IgniPaths.app_vm_profile(self._app_id))
        if response.status_code == 200:
            return self._parsed(response, AppVmProfile)
        raise self._failed(response)

    @staticmethod
    def _parsed[M: BaseModel](response: httpx.Response, model: type[M]) -> M:
        try:
            return model.model_validate(response.json())
        except (ValidationError, ValueError) as exc:
            raise IgniUnavailable("igni answered with something else") from exc

    @staticmethod
    def _failed(response: httpx.Response) -> Exception:
        if 400 <= response.status_code < 500 and response.status_code != 429:
            return refusal(response)
        return IgniUnavailable(f"igni answered {response.status_code}")
