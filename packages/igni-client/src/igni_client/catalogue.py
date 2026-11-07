"""The models an igni serves, by the name a session switches to."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from igni_client.connection import Connection


class ModelEntry(BaseModel):
    """One model igni can use. igni keeps more about each than this; the rest is kept too."""

    model_config = ConfigDict(extra="allow", protected_namespaces=())

    model_id: str = ""
    provider: str = ""
    context_window: int | None = None
    vision: bool = False


class ModelCatalogue(BaseModel):
    """The models igni can use, by the name a session switches to."""

    model_config = ConfigDict(populate_by_name=True)

    default: str
    max_context_window: int
    models: dict[str, ModelEntry] = Field(default_factory=dict, alias="registry")


class Models:
    """The models this igni serves."""

    CATALOGUE = TypeAdapter(ModelCatalogue)

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    async def list(self) -> ModelCatalogue:
        return await self._conn.rpc("get_model_registry", self.CATALOGUE)
