from __future__ import annotations

from dataclasses import replace
from copy import deepcopy

import pytest

from conftest import SCENARIOS, scenario_packet
from context_enrichment.application.intake import IntakeValidationError
from context_enrichment.application.service import EnrichmentService
from context_enrichment.domain.config import EnrichmentConfig
from context_enrichment.domain.models import DiagnosticSeverity, ProviderDiagnostic, ProviderQuery, ProviderResult
from context_enrichment.providers.base import ContextProvider
from context_enrichment.providers.mock import build_mock_providers
from context_enrichment.validation.harness import load_scenario, run_scenario


class ExplodingProvider(ContextProvider):
    provider_id = "mock_ticket_provider"

    def health_check(self):
        return ProviderDiagnostic(self.provider_id, "PROVIDER_HEALTHY", "healthy before injected exception", DiagnosticSeverity.INFO)

    def search(self, query: ProviderQuery) -> ProviderResult:
        raise RuntimeError("synthetic injected component exception")

    def retrieve(self, record_id: str) -> ProviderResult:
        raise RuntimeError("synthetic injected component exception")


def test_internal_provider_exception_becomes_safe_explicit_failure() -> None:
    scenario = load_scenario(SCENARIOS / "V15.json")
    service = EnrichmentService(config=EnrichmentConfig(enabled_providers=("mock_ticket_provider",)), providers=(ExplodingProvider(),))
    packet = service.enrich(scenario.alert)
    assert packet.execution_status.value == "ENRICHMENT_FAILED"
    assert packet.confidence.level.value == "INSUFFICIENT_CONTEXT"
    assert packet.provider_diagnostics[0].code == "INTERNAL_PROVIDER_EXCEPTION"


def test_invalid_input_is_not_collapsed_to_no_context() -> None:
    with pytest.raises(IntakeValidationError, match="INVALID_INPUT"):
        EnrichmentService().enrich({"alert_id": "bad", "schema_version": "alert_schema_v1", "payload": {"user": "jsmith"}})


def test_malformed_record_is_bounded_and_valid_record_survives() -> None:
    _, packet = scenario_packet("V17")
    assert {item.source_record_id for item in packet.related_context} == {"CHG-V17-GOOD"}
    assert any(item.code == "SCHEMA_INCOMPATIBILITY" and item.record_id == "TKT-V17-BAD" for item in packet.provider_diagnostics)


def test_partial_provider_failure_is_end_to_end_partial_enrichment() -> None:
    base = load_scenario(SCENARIOS / "V08.json")
    providers = build_mock_providers(base.provider_records, {"mock_change_provider": "PARTIAL"})
    packet = EnrichmentService(providers=providers).enrich(base.alert)
    assert packet.execution_status.value == "PARTIAL_ENRICHMENT"
    assert packet.confidence.level.value == "MEDIUM"
    assert any(item.code == "PROVIDER_PARTIAL" for item in packet.provider_diagnostics)


def test_missing_host_degrades_without_fabrication() -> None:
    base = load_scenario(SCENARIOS / "V08.json")
    records = deepcopy(base.provider_records)
    records["mock_change_provider"][0]["data"].pop("asset")
    packet = EnrichmentService(providers=build_mock_providers(records)).enrich(base.alert)
    assert packet.execution_status.value == "RELATED_CONTEXT_FOUND"
    assert packet.confidence.level.value == "MEDIUM"
    assert any("CONTEXT_HOST_MISSING" in item for item in packet.missing_information)
    feature = next(item for item in packet.correlation_results[0].features if item.feature_type == "HOST_MATCH")
    assert feature.value == "UNAVAILABLE"


def test_unresolved_context_user_cannot_join_by_host_alone() -> None:
    base = load_scenario(SCENARIOS / "V08.json")
    records = deepcopy(base.provider_records)
    records["mock_change_provider"][0]["data"].pop("actor")
    packet = EnrichmentService(providers=build_mock_providers(records)).enrich(base.alert)
    assert packet.related_context == ()
    assert packet.execution_status.value == "NO_RELIABLE_CONTEXT_FOUND"
    assert any("CONTEXT_USER_MISSING" in item for item in packet.missing_information)


def test_structurally_malformed_fixture_is_diagnosed_not_executed() -> None:
    base = load_scenario(SCENARIOS / "V15.json")
    records = {"mock_ticket_provider": [{"record_id": None, "schema_version": None, "data": "untrusted text"}]}
    packet = EnrichmentService(providers=build_mock_providers(records)).enrich(base.alert)
    assert packet.related_context == ()
    assert any(item.code == "SCHEMA_INCOMPATIBILITY" for item in packet.provider_diagnostics)


def test_duplicates_do_not_inflate_relationship_or_evidence() -> None:
    _, duplicate = scenario_packet("V18")
    _, single = scenario_packet("V08")
    assert len(duplicate.related_context) == 1
    assert len(duplicate.correlation_results) == 1
    assert len(duplicate.evidence_set.supporting) == len(single.evidence_set.supporting)
    assert any(item.startswith("DUPLICATE_RECORD_SUPPRESSED") for item in duplicate.confidence.degradation_factors)


def test_ambiguous_identity_never_collapses_to_relationship() -> None:
    base = load_scenario(SCENARIOS / "V08.json")
    config = EnrichmentConfig(user_aliases={"jsmith": ("user-a", "user-b")})
    service = EnrichmentService(config=config, providers=build_mock_providers(base.provider_records, base.provider_status))
    packet = service.enrich(base.alert)
    assert packet.related_context == ()
    assert packet.execution_status.value == "NO_RELIABLE_CONTEXT_FOUND"


def test_validation_fail_and_error_semantics_are_distinct() -> None:
    base = load_scenario(SCENARIOS / "V01.json")
    wrong = replace(base, expectation=replace(base.expectation, execution_status="ENRICHMENT_FAILED"))
    invalid_provider = replace(base, provider_status={"mock_ticket_provider": "INVALID"})
    assert run_scenario(wrong).outcome.value == "FAIL"
    assert run_scenario(invalid_provider).outcome.value == "ERROR"
