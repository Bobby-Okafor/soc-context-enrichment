"""Frozen raw context-provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from context_enrichment.domain.models import ProviderDiagnostic, ProviderQuery, ProviderResult


class ContextProvider(ABC):
    provider_id: str

    @abstractmethod
    def health_check(self) -> ProviderDiagnostic:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: ProviderQuery) -> ProviderResult:
        raise NotImplementedError

    @abstractmethod
    def retrieve(self, record_id: str) -> ProviderResult:
        raise NotImplementedError
