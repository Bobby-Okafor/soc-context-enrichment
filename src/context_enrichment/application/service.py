"""Frozen-sequence orchestration; domain algorithms remain in owned components."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

from context_enrichment.application.intake import validate_intake_envelope
from context_enrichment.application.query import construct_provider_queries
from context_enrichment.application.status import determine_execution_status
from context_enrichment.candidate_selection.selector import CandidateSelector
from context_enrichment.confidence.assessor import ConfidenceAssessor
from context_enrichment.correlation.engine import CorrelationEngine
from context_enrichment.domain.config import EnrichmentConfig
from context_enrichment.domain.models import (
    CanonicalContextRecord,
    DiagnosticSeverity,
    EnrichmentPacket,
    ProviderDiagnostic,
    ProviderStatus,
    RelationshipState,
)
from context_enrichment.domain.serialization import stable_id, to_primitive
from context_enrichment.entity_resolution.resolver import EntityResolver
from context_enrichment.evidence.builder import EvidenceBuilder
from context_enrichment.normalization.normalizers import AlertNormalizer, ContextNormalizer, NormalizationError
from context_enrichment.providers.base import ContextProvider
from context_enrichment.providers.mock import REPLAY_RETRIEVED_AT, build_mock_providers


LOGGER = logging.getLogger("context_enrichment")


class EnrichmentService:
    """Application service that owns sequencing and query construction only."""

    def __init__(
        self,
        config: EnrichmentConfig | None = None,
        providers: Iterable[ContextProvider] | None = None,
    ) -> None:
        self.config = config or EnrichmentConfig()
        self.providers = tuple(providers or build_mock_providers())
        self.alert_normalizer = AlertNormalizer(self.config)
        self.context_normalizer = ContextNormalizer(self.config)
        self.entity_resolver = EntityResolver(self.config)
        self.selector = CandidateSelector()
        self.correlator = CorrelationEngine(self.config)
        self.evidence_builder = EvidenceBuilder()
        self.confidence_assessor = ConfidenceAssessor()

    def enrich(self, alert_envelope: dict[str, Any]) -> EnrichmentPacket:
        raw_alert = validate_intake_envelope(alert_envelope)
        self._event("enrichment_started", alert_id=raw_alert.alert_id)
        alert = self.alert_normalizer.normalize(raw_alert)
        self._event("alert_normalized", alert_id=alert.alert_id, timestamp_quality=alert.timestamp.timestamp_quality.value)
        alert_entities = (
            self.entity_resolver.resolve_user(alert.user, f"alert:{alert.alert_id}:user"),
            self.entity_resolver.resolve_host(alert.host, f"alert:{alert.alert_id}:host"),
        )
        self._event("entity_resolution_completed", side="alert", count=len(alert_entities))

        enabled = tuple(provider.provider_id for provider in self.providers if provider.provider_id in self.config.enabled_providers)
        queries = construct_provider_queries(alert, alert_entities, enabled)
        provider_map = {provider.provider_id: provider for provider in self.providers}
        raw_records = []
        provider_diagnostics: list[ProviderDiagnostic] = []
        provider_summaries: list[dict[str, Any]] = []
        for query in queries:
            provider = provider_map[query.provider_id]
            try:
                result = provider.search(query)
            except Exception as exc:  # application boundary converts unexpected provider faults safely
                result = None
                provider_diagnostics.append(ProviderDiagnostic(provider.provider_id, "INTERNAL_PROVIDER_EXCEPTION", f"Provider raised {type(exc).__name__}", DiagnosticSeverity.ERROR))
                provider_summaries.append({"provider_id": provider.provider_id, "query_id": query.query_id, "status": "FAILED", "record_count": 0, "diagnostic_codes": ("INTERNAL_PROVIDER_EXCEPTION",)})
                self._event("provider_failed", provider_id=provider.provider_id, failure="internal_exception")
            if result is None:
                continue
            raw_records.extend(result.records)
            provider_diagnostics.extend(result.diagnostics)
            provider_summaries.append({"provider_id": provider.provider_id, "query_id": query.query_id, "status": result.status.value, "record_count": len(result.records), "diagnostic_codes": tuple(item.code for item in result.diagnostics)})
            event = "provider_failed" if result.status is ProviderStatus.FAILED else "provider_partially_failed" if result.status is ProviderStatus.PARTIAL else "provider_queried"
            self._event(event, provider_id=provider.provider_id, status=result.status.value, record_count=len(result.records))

        canonical_pairs: list[tuple[CanonicalContextRecord, tuple]] = []
        context_resolution_summaries: list[dict[str, Any]] = []
        normalization_diagnostics: list[str] = list(alert.diagnostics)
        for raw in sorted(raw_records, key=lambda item: (item.source_provider, item.source_record_id, item.source_schema_version)):
            try:
                record = self.context_normalizer.normalize(raw)
            except NormalizationError as exc:
                code = "SCHEMA_INCOMPATIBILITY" if str(exc).startswith("SCHEMA_INCOMPATIBILITY") else "NORMALIZATION_FAILURE"
                provider_diagnostics.append(ProviderDiagnostic(raw.source_provider, code, str(exc), DiagnosticSeverity.ERROR, raw.source_record_id))
                normalization_diagnostics.append(f"{code}:{raw.source_provider}:{raw.source_record_id}")
                continue
            entities = (
                self.entity_resolver.resolve_user(record.user, f"context:{record.source_provider}:{record.source_record_id}:user"),
                self.entity_resolver.resolve_host(record.host, f"context:{record.source_provider}:{record.source_record_id}:host"),
            )
            for record_diagnostic in record.diagnostics:
                if record_diagnostic.startswith("CONTEXT_TIMESTAMP_"):
                    provider_diagnostics.append(ProviderDiagnostic(
                        record.source_provider,
                        record_diagnostic,
                        f"Timestamp quality for {record.source_record_id}: {record.timestamp.timestamp_quality.value}",
                        DiagnosticSeverity.WARNING,
                        record.source_record_id,
                    ))
            normalization_diagnostics.extend(f"{item}:{record.source_provider}:{record.source_record_id}" for item in record.diagnostics)
            canonical_pairs.append((record, entities))
            context_resolution_summaries.append({"provider_id": record.source_provider, "record_id": record.source_record_id, "entities": to_primitive(entities)})
        self._event("entity_resolution_completed", side="context", count=len(canonical_pairs))

        selection = self.selector.select(alert, alert_entities, tuple(canonical_pairs))
        normalization_diagnostics.extend(selection.diagnostics)
        self._event("candidate_count", count=len(selection.candidates), rejected_count=len(selection.rejected_record_ids))
        correlated = tuple((candidate, self.correlator.correlate(alert, alert_entities, candidate)) for candidate in selection.candidates)
        results = tuple(result for _, result in correlated)
        self._event("correlation_completed", count=len(results))
        evidence = self.evidence_builder.build(correlated)
        self._event("evidence_created", supporting=len(evidence.supporting), contradicting=len(evidence.contradicting))
        diagnostics = tuple(sorted(provider_diagnostics, key=lambda item: (item.provider_id, item.code, item.record_id or "")))
        confidence = self.confidence_assessor.assess(results, evidence, diagnostics, tuple(sorted(set(normalization_diagnostics))))
        self._event("confidence_assessed", level=confidence.level.value)
        status = determine_execution_status(results, diagnostics)

        record_by_key = {(record.source_provider, record.source_record_id): record for record, _ in canonical_pairs}
        related = tuple(
            record_by_key[(result.source_provider, result.context_record_reference)]
            for result in results
            if result.relationship_state in {RelationshipState.SUPPORTED, RelationshipState.PARTIALLY_SUPPORTED}
        )
        contradictions = tuple(sorted(
            f"{result.source_provider}:{result.context_record_reference}:{feature.feature_type}:{feature.value}"
            for result in results
            for feature in result.features
            if feature.value in {"CONTRADICTORY", "REJECTED", "CANCELLED", "MISMATCH"}
        ))
        missing = tuple(sorted(set(
            [item for item in normalization_diagnostics if any(token in item for token in ("MISSING", "MALFORMED", "AMBIGUOUS", "FAILURE", "INCOMPATIBILITY"))]
            + [f"{item.provider_id}:{item.code}" for item in diagnostics if item.severity is DiagnosticSeverity.ERROR]
        )))
        review = []
        if contradictions:
            review.append("Review explicit contradictory source observations and record state")
        if missing:
            review.append("Review missing, malformed, or unavailable source information")
        if status.value == "AMBIGUOUS_CONTEXT":
            review.append("Compare materially competing context records")
        provenance = {
            "pipeline_version": "context_enrichment_v1",
            "architecture_version": "1.1",
            "assembled_at": REPLAY_RETRIEVED_AT,
            "provider_count": len(enabled),
            "pipeline_stages": (
                "INTAKE_VALIDATED", "ALERT_NORMALIZED", "ALERT_ENTITIES_RESOLVED",
                "PROVIDER_QUERIES_CONSTRUCTED", "PROVIDERS_QUERIED", "CONTEXT_NORMALIZED",
                "CONTEXT_ENTITIES_RESOLVED", "CANDIDATES_SELECTED", "CORRELATION_EVALUATED",
                "EVIDENCE_CONSTRUCTED", "CONFIDENCE_ASSESSED", "EXECUTION_STATUS_DETERMINED",
                "PACKET_ASSEMBLED",
            ),
            "alert_resolved_entities": to_primitive(alert_entities),
            "provider_results": tuple(sorted(provider_summaries, key=lambda item: item["provider_id"])),
            "context_resolution": tuple(sorted(context_resolution_summaries, key=lambda item: (item["provider_id"], item["record_id"]))),
            "selected_candidates": tuple({
                "provider_id": item.record.source_provider,
                "record_id": item.record.source_record_id,
                "selection_reasons": item.selection_reasons,
                "entity_specificity": item.entity_specificity,
                "temporal_distance_seconds": item.temporal_distance_seconds,
            } for item in selection.candidates),
            "selected_candidate_record_ids": tuple(item.record.source_record_id for item in selection.candidates),
            "rejected_candidate_record_ids": selection.rejected_record_ids,
            "rejected_candidates": tuple({"record_id": record_id, "reason": reason} for record_id, reason in selection.rejected_reasons),
            "transformation_chain": ("raw_alert_v1", "canonical_alert_v1", "enrichment_packet_v1"),
        }
        identity_material = {
            "alert": to_primitive(alert), "status": status.value,
            "related": [(item.source_provider, item.source_record_id) for item in related],
            "correlations": to_primitive(results), "evidence": to_primitive(evidence),
            "confidence": to_primitive(confidence), "diagnostics": to_primitive(diagnostics),
        }
        packet = EnrichmentPacket(
            packet_id=stable_id("packet", identity_material),
            schema_version="enrichment_packet_v1",
            alert=alert,
            execution_status=status,
            related_context=related,
            correlation_results=results,
            evidence_set=evidence,
            confidence=confidence,
            contradictions=contradictions,
            missing_information=missing,
            provider_diagnostics=diagnostics,
            recommended_review_areas=tuple(review),
            provenance=provenance,
        )
        self._event("packet_assembled", packet_id=packet.packet_id, execution_status=status.value)
        return packet

    @staticmethod
    def _event(event: str, **fields: Any) -> None:
        LOGGER.info(json.dumps({"event": event, **fields}, sort_keys=True))
