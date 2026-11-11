"""Base class for immutable, always-valid domain models."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Frozen, extra-forbidding model whose copies are re-validated.

    Pydantic's ``model_copy(update=...)`` normally skips validation; here an update goes
    through ``model_validate`` so no domain object can exist in an invalid state.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        if not update:
            return super().model_copy(deep=deep)
        data = {name: getattr(self, name) for name in type(self).model_fields}
        data.update(update)
        return type(self).model_validate(data)
