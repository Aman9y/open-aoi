"""Shared FastAPI dependencies (singletons)."""

from __future__ import annotations

from functools import lru_cache

from ..config import Settings, get_settings
from ..storage.inspection_repository import InspectionRepository
from ..storage.reference_repository import ReferenceRepository


@lru_cache
def reference_repo() -> ReferenceRepository:
    return ReferenceRepository(get_settings())


@lru_cache
def inspection_repo() -> InspectionRepository:
    return InspectionRepository(get_settings())


def settings() -> Settings:
    return get_settings()
