"""Five deterministic fixture-backed providers returning raw records only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from context_enrichment.domain.models import (
    DiagnosticSeverity,
    ProviderDiagnostic,
    ProviderQuery,
    ProviderResult,
    ProviderStatus,
    RawProviderRecord,
)
from context_enrichment.providers.base import ContextProvider


REPLAY_RETRIEVED_AT = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


class FixtureProvider(ContextProvider):
    provider_id = "fixture_provider"

    def __init__(self, records: Iterable[dict[str, Any]] = (), *, status: ProviderStatus = ProviderStatus.SUCCESS) -> None:
        self._status = status
        self._records = tuple(self._decode(item) for item in records)

    def _decode(self, value: dict[str, Any]) -> RawProviderRecord:
        record_id = value.get("record_id")
        schema_version = value.get("schema_version")
        data = value.get("data")
        if not isinstance(record_id, str) or not isinstance(schema_version, str) or not isinstance(data, dict):
            # Preserve malformed representation so normalization can diagnose it.
            record_id = str(record_id or "malformed-record")
            schema_version = str(schema_version or "unknown_schema")
            data = dict(data) if isinstance(data, dict) else {"malformed_payload": data}
        return RawProviderRecord(self.provider_id, record_id, schema_version, REPLAY_RETRIEVED_AT, data)

    def health_check(self) -> ProviderDiagnostic:
        if self._status is ProviderStatus.FAILED:
            return ProviderDiagnostic(self.provider_id, "PROVIDER_UNAVAILABLE", "Synthetic provider is configured unavailable", DiagnosticSeverity.ERROR)
        if self._status is ProviderStatus.PARTIAL:
            return ProviderDiagnostic(self.provider_id, "PROVIDER_PARTIAL", "Synthetic provider is configured partially available", DiagnosticSeverity.WARNING)
        return ProviderDiagnostic(self.provider_id, "PROVIDER_HEALTHY", "Synthetic provider is available", DiagnosticSeverity.INFO)

    def search(self, query: ProviderQuery) -> ProviderResult:
        if query.provider_id != self.provider_id:
            diagnostic = ProviderDiagnostic(self.provider_id, "QUERY_PROVIDER_MISMATCH", "ProviderQuery target does not match provider", DiagnosticSeverity.ERROR)
            return ProviderResult(self.provider_id, ProviderStatus.FAILED, (), (diagnostic,))
        health = self.health_check()
        if self._status is ProviderStatus.FAILED:
            return ProviderResult(self.provider_id, ProviderStatus.FAILED, (), (health,))
        diagnostics = () if self._status is ProviderStatus.SUCCESS else (health,)
        return ProviderResult(self.provider_id, self._status, self._records, diagnostics)

    def retrieve(self, record_id: str) -> ProviderResult:
        if self._status is ProviderStatus.FAILED:
            return ProviderResult(self.provider_id, ProviderStatus.FAILED, (), (self.health_check(),))
        matches = tuple(record for record in self._records if record.source_record_id == record_id)
        if not matches:
            diagnostic = ProviderDiagnostic(self.provider_id, "RECORD_NOT_FOUND", f"Synthetic record not found: {record_id}", DiagnosticSeverity.WARNING, record_id)
            return ProviderResult(self.provider_id, ProviderStatus.SUCCESS, (), (diagnostic,))
        return ProviderResult(self.provider_id, self._status, matches, ())


class MockTicketProvider(FixtureProvider):
    provider_id = "mock_ticket_provider"


class MockChangeProvider(FixtureProvider):
    provider_id = "mock_change_provider"


class MockHistoricalCaseProvider(FixtureProvider):
    provider_id = "mock_historical_case_provider"


class MockIdentityProvider(FixtureProvider):
    provider_id = "mock_identity_provider"


class MockAssetProvider(FixtureProvider):
    provider_id = "mock_asset_provider"


PROVIDER_CLASSES = {
    "mock_ticket_provider": MockTicketProvider,
    "mock_change_provider": MockChangeProvider,
    "mock_historical_case_provider": MockHistoricalCaseProvider,
    "mock_identity_provider": MockIdentityProvider,
    "mock_asset_provider": MockAssetProvider,
}


def build_mock_providers(
    records: dict[str, list[dict[str, Any]]] | None = None,
    statuses: dict[str, str] | None = None,
) -> tuple[ContextProvider, ...]:
    records = records or {}
    statuses = statuses or {}
    providers: list[ContextProvider] = []
    for provider_id, provider_class in PROVIDER_CLASSES.items():
        try:
            status = ProviderStatus(statuses.get(provider_id, ProviderStatus.SUCCESS.value))
        except ValueError as exc:
            raise ValueError(f"invalid provider status for {provider_id}") from exc
        providers.append(provider_class(records.get(provider_id, ()), status=status))
    return tuple(providers)
