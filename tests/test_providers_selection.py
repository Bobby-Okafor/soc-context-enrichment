from __future__ import annotations

from datetime import datetime, timezone

from context_enrichment.application.query import construct_provider_queries
from context_enrichment.application.intake import validate_intake_envelope
from context_enrichment.candidate_selection.selector import CandidateSelector
from context_enrichment.domain.config import DEFAULT_PROVIDERS, EnrichmentConfig
from context_enrichment.domain.models import ProviderStatus, RawProviderRecord
from context_enrichment.entity_resolution.resolver import EntityResolver
from context_enrichment.normalization.normalizers import AlertNormalizer, ContextNormalizer
from context_enrichment.providers.mock import build_mock_providers


def test_five_required_providers_and_health_contract() -> None:
    providers = build_mock_providers()
    assert tuple(item.provider_id for item in providers) == DEFAULT_PROVIDERS
    assert all(item.health_check().code == "PROVIDER_HEALTHY" for item in providers)


def test_provider_failure_is_not_an_empty_success() -> None:
    providers = build_mock_providers(statuses={"mock_ticket_provider": "FAILED"})
    provider = providers[0]
    query = _query(provider.provider_id)
    result = provider.search(query)
    assert result.status is ProviderStatus.FAILED
    assert result.records == ()
    assert result.diagnostics[0].code == "PROVIDER_UNAVAILABLE"


def test_successful_empty_provider_is_distinct() -> None:
    provider = build_mock_providers()[0]
    result = provider.search(_query(provider.provider_id))
    assert result.status is ProviderStatus.SUCCESS
    assert result.records == ()
    assert result.diagnostics == ()


def test_provider_retrieve_is_deterministic() -> None:
    records = {"mock_ticket_provider": [{"record_id": "r1", "schema_version": "ticket_schema_v1", "data": {"record_type": "ticket"}}]}
    provider = build_mock_providers(records)[0]
    assert provider.retrieve("r1").records[0].source_record_id == "r1"
    missing = provider.retrieve("absent")
    assert missing.status is ProviderStatus.SUCCESS and missing.diagnostics[0].code == "RECORD_NOT_FOUND"


def test_query_construction_is_generic_and_stably_ordered() -> None:
    config = EnrichmentConfig()
    alert = AlertNormalizer(config).normalize(validate_intake_envelope({"alert_id": "a", "schema_version": "alert_schema_v1", "payload": {"observed_at": "2026-01-15T10:00:00Z", "user": "jsmith", "host": "HOST-A", "action": "account_unlock"}}))
    resolver = EntityResolver(config)
    entities = (resolver.resolve_user(alert.user, "alert"), resolver.resolve_host(alert.host, "alert"))
    queries = construct_provider_queries(alert, entities, ("mock_ticket_provider", "mock_asset_provider"))
    assert [item.provider_id for item in queries] == ["mock_asset_provider", "mock_ticket_provider"]
    assert all(item.canonical_user == "jsmith" for item in queries)


def test_candidate_selection_orders_and_suppresses_duplicates() -> None:
    config = EnrichmentConfig()
    normalizer = ContextNormalizer(config)
    resolver = EntityResolver(config)
    alert = AlertNormalizer(config).normalize(validate_intake_envelope({"alert_id": "a", "schema_version": "alert_schema_v1", "payload": {"observed_at": "2026-01-15T10:00:00Z", "user": "jsmith", "host": "WEB-PRD-01", "action": "privileged_password_change"}}))
    alert_entities = (resolver.resolve_user(alert.user, "alert"), resolver.resolve_host(alert.host, "alert"))
    values = [
        ("late", "2026-01-15T09:40:00Z"),
        ("near", "2026-01-15T09:55:00Z"),
        ("near", "2026-01-15T09:55:00Z"),
    ]
    pairs = []
    for record_id, stamp in values:
        raw = RawProviderRecord("mock_ticket_provider", record_id, "ticket_schema_v1", datetime(2026, 1, 15, tzinfo=timezone.utc), {"record_type": "ticket", "created": stamp, "requester": "jsmith", "target_host": "WEB-PRD-01", "request_type": "password_reset", "status": "approved"})
        record = normalizer.normalize(raw)
        pairs.append((record, (resolver.resolve_user(record.user, record_id), resolver.resolve_host(record.host, record_id))))
    selected = CandidateSelector().select(alert, alert_entities, tuple(pairs))
    assert [item.record.source_record_id for item in selected.candidates] == ["near", "late"]
    assert selected.diagnostics == ("DUPLICATE_RECORD_SUPPRESSED:mock_ticket_provider:near",)
    assert all(item.selection_reasons for item in selected.candidates)


def test_host_only_does_not_select_known_user_mismatch() -> None:
    from conftest import scenario_packet
    _, packet = scenario_packet("V06")
    assert packet.provenance["selected_candidate_record_ids"] == ()
    assert packet.related_context == ()
    assert packet.provenance["rejected_candidates"] == ({"record_id": "CHG-V06-USER", "reason": "EXPLICIT_USER_MISMATCH"},)


def test_partial_provider_status_preserves_usable_records_and_diagnostic() -> None:
    records = {"mock_ticket_provider": [{"record_id": "partial-1", "schema_version": "ticket_schema_v1", "data": {"record_type": "ticket"}}]}
    provider = build_mock_providers(records, {"mock_ticket_provider": "PARTIAL"})[0]
    result = provider.search(_query(provider.provider_id))
    assert result.status is ProviderStatus.PARTIAL
    assert len(result.records) == 1
    assert result.diagnostics[0].code == "PROVIDER_PARTIAL"


def _query(provider_id: str):
    from context_enrichment.domain.models import ProviderQuery
    return ProviderQuery("q", "a", provider_id, "jsmith", "host", "password_reset", datetime(2026, 1, 15, tzinfo=timezone.utc))
