"""Screen-share-ready deterministic demonstration adapter for the CLI."""

from dataclasses import dataclass
from pathlib import Path

from context_enrichment.application.service import EnrichmentService
from context_enrichment.assistant.contracts import AssistantIntent, AssistantRequest, AssistantResponse
from context_enrichment.assistant.model_adapter import ModelAdapter
from context_enrichment.assistant.service import AnalystAssistant
from context_enrichment.domain.config import EnrichmentConfig
from context_enrichment.domain.models import EnrichmentPacket
from context_enrichment.domain.serialization import canonical_json
from context_enrichment.providers.mock import build_mock_providers
from context_enrichment.validation.harness import load_scenario, validate_fixture_path


DEMO_SCENARIOS = {"primary": "V01.json", "false-join": "V04.json", "provider-failure": "V16.json"}


@dataclass(frozen=True)
class DemoResult:
    scenario_key: str
    scenario_id: str
    scenario_name: str
    packet: EnrichmentPacket
    response: AssistantResponse


def run_demo(
    scenario_key: str = "primary",
    *,
    fixture_root: Path = Path("fixtures"),
    model_adapter: ModelAdapter | None = None,
) -> DemoResult:
    if scenario_key not in DEMO_SCENARIOS:
        raise ValueError(f"unknown demo scenario: {scenario_key}")
    root = fixture_root.resolve()
    path = validate_fixture_path(root / "scenarios" / DEMO_SCENARIOS[scenario_key], root)
    scenario = load_scenario(path, root)
    service = EnrichmentService(
        config=EnrichmentConfig(fixture_root=root),
        providers=build_mock_providers(scenario.provider_records, scenario.provider_status),
    )
    assistant = AnalystAssistant(service, model_adapter=model_adapter)
    request = AssistantRequest.for_alert(AssistantIntent.ENRICH_ALERT, scenario.alert)
    response = assistant.execute(request)
    packet = service.enrich(scenario.alert)
    if packet.packet_id != response.packet_id:
        raise RuntimeError("deterministic demo packet reference mismatch")
    return DemoResult(scenario_key, scenario.scenario_id, scenario.name, packet, response)


def render_demo(result: DemoResult) -> str:
    packet = result.packet
    response = result.response
    provenance = packet.provenance
    lines = [
        "SOC CONTEXT ENRICHMENT — ANALYST ASSISTANT DEMO",
        f"Scenario: {result.scenario_key} ({result.scenario_id}: {result.scenario_name})",
        "",
        "ALERT",
        f"- {packet.alert.alert_id}: action={packet.alert.action} user={packet.alert.user} host={packet.alert.host}",
        f"- observed={packet.alert.timestamp.normalized_timestamp.isoformat()} quality={packet.alert.timestamp.timestamp_quality.value}" if packet.alert.timestamp.normalized_timestamp else f"- observed unavailable; quality={packet.alert.timestamp.timestamp_quality.value}",
        "",
        "CONTEXT DISCOVERY",
    ]
    lines.extend(f"- {item['provider_id']}: {item['status']} records={item['record_count']}" for item in provenance.get("provider_results", ()))
    lines.extend(["", "ENTITY RESOLUTION"])
    lines.extend(f"- {item['entity_type']}: {item['input_value']} -> {item['canonical_value']} ({item['resolution_quality']})" for item in provenance.get("alert_resolved_entities", ()))
    lines.extend(["", "CORRELATION"])
    lines.extend(f"- {item.source_provider}/{item.context_record_reference}: {item.relationship_state.value}" for item in packet.correlation_results)
    if not packet.correlation_results:
        lines.append("- No candidate relationship safely passed correlation")
    lines.extend(f"- REJECTED {item['record_id']}: {item['reason']}" for item in provenance.get("rejected_candidates", ()))
    lines.extend(["", "EVIDENCE"])
    state_by_record = {(item.source_provider, item.context_record_reference): item.relationship_state.value for item in packet.correlation_results}
    accepted_states = {"SUPPORTED", "PARTIALLY_SUPPORTED"}
    relationship_support = tuple(item for item in packet.evidence_set.supporting if state_by_record.get((item.source_provider, item.source_record_id)) in accepted_states)
    nonrelationship_observations = tuple(item for item in packet.evidence_set.supporting if item not in relationship_support)
    lines.extend(f"- SUPPORT [{item.evidence_id}] {item.claim_type}={item.canonical_values.get('feature_value')}" for item in relationship_support)
    if nonrelationship_observations:
        lines.append(f"- {len(nonrelationship_observations)} feature observations belong to NOT_SUPPORTED records and are not relationship support")
    lines.extend(f"- CONTRADICT [{item.evidence_id}] {item.claim_type}={item.canonical_values.get('feature_value')}" for item in packet.evidence_set.contradicting)
    if not packet.evidence_set.supporting and not packet.evidence_set.contradicting:
        lines.append("- No qualifying evidence; no evidence was fabricated")
    lines.extend(["", "CONFIDENCE", f"- {packet.confidence.level.value}"])
    lines.extend(f"- {item}" for item in packet.confidence.rationale)
    lines.extend(["", "ASSISTANT WORKFLOW", f"- Intent: {response.intent.value}"])
    lines.append("- Plan: " + " -> ".join(action.value for action in response.trace.deterministic_plan))
    lines.extend(f"- Tool {call.sequence}: {call.tool_name} [{call.status}] refs={', '.join(call.output_references) or 'none'}" for call in response.trace.tool_calls)
    lines.extend(["", "ANALYST RESPONSE"])
    lines.extend(response.narrative.splitlines())
    lines.extend([
        "",
        "SAFETY / LIMITATIONS",
        "- Deterministic synthetic demonstration; no external model, network, credential, or production connector",
        "- The assistant consumes accepted packet authority and cannot change correlation, evidence, or confidence",
        "- Review suggestions are not response actions; analyst judgment remains authoritative",
    ])
    return "\n".join(lines) + "\n"


def render_demo_json(result: DemoResult) -> str:
    return canonical_json({
        "scenario_key": result.scenario_key,
        "scenario_id": result.scenario_id,
        "scenario_name": result.scenario_name,
        "packet": result.packet,
        "assistant_response": result.response,
    })
