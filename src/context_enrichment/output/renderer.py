"""Deterministic analyst-facing packet renderer; this is not AI."""

from __future__ import annotations

from context_enrichment.domain.models import EnrichmentPacket


def render_packet(packet: EnrichmentPacket) -> str:
    lines = [
        "SOC CONTEXT ENRICHMENT PACKET",
        f"Packet: {packet.packet_id}",
        f"Alert: {packet.alert.alert_id}",
        f"Execution status: {packet.execution_status.value}",
        f"Relationship confidence: {packet.confidence.level.value}",
        "",
        "Executed pipeline stages:",
    ]
    lines.extend(f"- {stage}" for stage in packet.provenance.get("pipeline_stages", ()))
    lines.extend(["", "Resolved alert entities:"])
    lines.extend(
        f"- {item['entity_type']}: input={item['input_value']} canonical={item['canonical_value']} method={item['resolution_method']} quality={item['resolution_quality']}"
        for item in packet.provenance.get("alert_resolved_entities", ())
    )
    lines.extend(["", "Provider query results:"])
    lines.extend(
        f"- {item['provider_id']}: {item['status']} records={item['record_count']} query={item['query_id']}"
        for item in packet.provenance.get("provider_results", ())
    )
    lines.extend(["", "Candidate selection:"])
    lines.extend(
        f"- SELECTED {item['provider_id']}/{item['record_id']}: {', '.join(item['selection_reasons'])}"
        for item in packet.provenance.get("selected_candidates", ())
    )
    lines.extend(
        f"- REJECTED {item['record_id']}: {item['reason']}"
        for item in packet.provenance.get("rejected_candidates", ())
    )
    if not packet.provenance.get("selected_candidates") and not packet.provenance.get("rejected_candidates"):
        lines.append("- No retrieved record qualified or required explicit rejection")
    lines.extend([
        "",
        "Related context:",
    ])
    if packet.related_context:
        lines.extend(f"- {item.source_provider}/{item.source_record_id} [{item.record_type}] state={item.record_state}" for item in packet.related_context)
    else:
        lines.append("- None safely supported")
    lines.extend(["", "Correlation results:"])
    lines.extend(
        f"- {item.source_provider}/{item.context_record_reference}: {item.relationship_state.value} ({', '.join(feature.feature_type + '=' + feature.value for feature in item.features)})"
        for item in packet.correlation_results
    )
    lines.extend(["", f"Supporting evidence: {len(packet.evidence_set.supporting)}"])
    for item in packet.evidence_set.supporting:
        lines.append(f"- SUPPORT {item.evidence_id} {item.source_provider}/{item.source_record_id} {item.claim_type}={item.canonical_values['feature_value']}")
    lines.append(f"Contradicting evidence: {len(packet.evidence_set.contradicting)}")
    for item in packet.evidence_set.contradicting:
        lines.append(f"- CONTRADICTION {item.source_provider}/{item.source_record_id} {item.claim_type}={item.canonical_values['feature_value']}")
    lines.extend(["", "Missing information:"])
    lines.extend(f"- {item}" for item in packet.missing_information)
    if not packet.missing_information:
        lines.append("- None")
    lines.extend(["", "Recommended review areas:"])
    lines.extend(f"- {item}" for item in packet.recommended_review_areas)
    if not packet.recommended_review_areas:
        lines.append("- None")
    lines.extend(["", "Source provenance:"])
    for item in packet.related_context:
        lines.append(
            f"- {item.source_provider}/{item.source_record_id}: schema={item.source_schema_version} "
            f"retrieved={item.provenance.retrieved_at.isoformat()} chain={'>'.join(item.provenance.transformation_chain)}"
        )
    lines.extend(["", "This packet supplies deterministic context only; analyst judgment remains authoritative."])
    return "\n".join(lines) + "\n"
