"""`IgniCallbacks`: what the service answers when igni calls it.

igni calls a service to erase or export one person's data in one
organisation (`igni_service.subjects`), and when it deletes an
organisation (`igni_service.organisations`). The service registers a
handler for each with `@igni.on_erase`, `@igni.on_export` and
`@igni.on_organisation_deleted`; `igni.router` is the routes igni calls.
"""

from __future__ import annotations

from fastapi import APIRouter

from igni_service.directory import DirectoryClient
from igni_service.organisations import (
    IgniCaller,
    OrganisationDeletedHandler,
    OrganisationHandlers,
    OrganisationRoutes,
)
from igni_service.subjects import EraseHandler, ExportHandler, SubjectHandlers, SubjectRoutes


class IgniCallbacks:
    """The service's handlers for igni's calls, and the routes that call them.

    Args:
        directory: igni's directory, which a person's subject is resolved in.
        igni_call: The dependency that checks a call is igni's own.
    """

    def __init__(self, directory: DirectoryClient, igni_call: IgniCaller) -> None:
        self._subjects = SubjectHandlers()
        self._organisations = OrganisationHandlers()
        self._directory = directory
        self._igni_call = igni_call
        self._router: APIRouter | None = None

    def on_erase(self, handler: EraseHandler) -> EraseHandler:
        """Register what erases one person's data in one organisation.

        Args:
            handler: What to call when igni asks for one person's data to be
                erased or redacted.
        """
        return self._subjects.on_erase(handler)

    def on_export(self, handler: ExportHandler) -> ExportHandler:
        """Register what lists one person's data in one organisation.

        Args:
            handler: What to call when igni asks what the service holds
                about one person.
        """
        return self._subjects.on_export(handler)

    def on_organisation_deleted(
        self, handler: OrganisationDeletedHandler
    ) -> OrganisationDeletedHandler:
        """Register what stops routing to an organisation igni deleted.

        Args:
            handler: What to call when igni says an organisation was deleted.
        """
        return self._organisations.on_deleted(handler)

    @property
    def router(self) -> APIRouter:
        """The routes igni calls, made once."""
        if self._router is None:
            router = APIRouter()
            router.include_router(
                SubjectRoutes(self._subjects, self._directory, self._igni_call).router()
            )
            router.include_router(OrganisationRoutes(self._organisations, self._igni_call).router())
            self._router = router
        return self._router
