"""Narrow controlled tools over EnrichmentService and accepted packets."""

from typing import Any

from context_enrichment.application.service import EnrichmentService
from context_enrichment.domain.models import EnrichmentPacket


class AssistantTools:
    def __init__(self, enrichment_service: EnrichmentService) -> None:
        self._enrichment_service = enrichment_service

    def enrich_alert(self, alert_envelope: dict[str, Any]) -> EnrichmentPacket:
        return self._enrichment_service.enrich(alert_envelope)

    @staticmethod
    def get_relationship(packet: EnrichmentPacket) -> tuple:
        return packet.correlation_results

    @staticmethod
    def get_supporting_evidence(packet: EnrichmentPacket) -> tuple:
        return packet.evidence_set.supporting

    @staticmethod
    def get_contradicting_evidence(packet: EnrichmentPacket) -> tuple:
        return packet.evidence_set.contradicting

    @staticmethod
    def get_missing_information(packet: EnrichmentPacket) -> tuple[str, ...]:
        return packet.missing_information

    @staticmethod
    def get_confidence_factors(packet: EnrichmentPacket):
        return packet.confidence

    @staticmethod
    def get_provider_diagnostics(packet: EnrichmentPacket) -> tuple:
        return packet.provider_diagnostics

    @staticmethod
    def get_recommended_review_areas(packet: EnrichmentPacket) -> tuple[str, ...]:
        return packet.recommended_review_areas
