"""Thin CLI adapter over application, output, and validation services."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from context_enrichment.application.service import EnrichmentService
from context_enrichment.cli.demo import render_demo, render_demo_json, run_demo
from context_enrichment.domain.config import EnrichmentConfig
from context_enrichment.domain.serialization import canonical_json
from context_enrichment.output.renderer import render_packet
from context_enrichment.providers.mock import build_mock_providers
from context_enrichment.validation.harness import load_scenario, run_validation_directory, validate_fixture_path, write_validation_outputs
from context_enrichment.validation.demo_layer import build_demo_layer_report, write_demo_layer_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="context-enrichment")
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    enrich = sub.add_parser("enrich", help="Run one synthetic scenario through EnrichmentService")
    enrich.add_argument("scenario")
    enrich.add_argument("--output")
    enrich.add_argument("--fixture-root", default="fixtures")
    render = sub.add_parser("render", help="Render a serialized packet deterministically")
    render.add_argument("packet")
    render.add_argument("--output")
    validate = sub.add_parser("validate", help="Run replay validation scenarios")
    validate.add_argument("--scenarios", default="fixtures/scenarios")
    validate.add_argument("--output", default="validation/validation-report.json")
    validate.add_argument("--markdown", default="validation/VALIDATION_REPORT.md")
    validate.add_argument("--fixture-root", default="fixtures")
    demo = sub.add_parser("demo", help="Run the deterministic AnalystAssistant demonstration")
    demo.add_argument("--scenario", choices=("primary", "false-join", "provider-failure"), default="primary")
    demo.add_argument("--fixture-root", default="fixtures")
    demo.add_argument("--json", action="store_true", dest="json_output")
    demo.add_argument("--output")
    demo_validate = sub.add_parser("demo-validate", help="Generate deterministic demo-layer validation evidence")
    demo_validate.add_argument("--repository", default=".")
    demo_validate.add_argument("--fixture-root", default="fixtures")
    demo_validate.add_argument("--output", default="validation/demo-layer/demo-layer-validation.json")
    demo_validate.add_argument("--markdown", default="validation/demo-layer/DEMO_LAYER_VALIDATION.md")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")
    if args.command == "enrich":
        fixture_root = Path(args.fixture_root).resolve()
        scenario_path = validate_fixture_path(Path(args.scenario), fixture_root)
        scenario = load_scenario(scenario_path, fixture_root)
        service = EnrichmentService(config=EnrichmentConfig(fixture_root=fixture_root), providers=build_mock_providers(scenario.provider_records, scenario.provider_status))
        packet = service.enrich(scenario.alert)
        value = canonical_json(packet)
        _emit(value, args.output)
        return 0
    if args.command == "render":
        value = json.loads(Path(args.packet).read_text(encoding="utf-8"))
        rendered = render_serialized_packet(value)
        _emit(rendered, args.output)
        return 0
    if args.command == "validate":
        fixture_root = Path(args.fixture_root).resolve()
        report = run_validation_directory(Path(args.scenarios), fixture_root)
        write_validation_outputs(report, Path(args.output), Path(args.markdown))
        print(f"validation: {report.pass_count}/{report.scenario_count} PASS; false_associations={report.false_association_count}; errors={report.error_count}")
        return 0 if report.fail_count == 0 and report.error_count == 0 and report.false_association_count == 0 else 1
    if args.command == "demo":
        result = run_demo(args.scenario, fixture_root=Path(args.fixture_root))
        value = render_demo_json(result) if args.json_output else render_demo(result)
        _emit(value, args.output)
        return 0
    if args.command == "demo-validate":
        report = build_demo_layer_report(Path(args.repository), Path(args.fixture_root))
        write_demo_layer_report(report, Path(args.output), Path(args.markdown))
        print(f"demo-layer validation: {report['pass_count']}/{report['check_count']} PASS; false_associations={report['false_association_count']}; errors={report['error_count']}")
        return 0 if report["passed"] else 1
    return 2


def render_serialized_packet(value: dict) -> str:
    # Adapter reconstruction is deliberately presentation-only.
    lines = [
        "SOC CONTEXT ENRICHMENT PACKET",
        f"Packet: {value['packet_id']}",
        f"Alert: {value['alert']['alert_id']}",
        f"Execution status: {value['execution_status']}",
        f"Relationship confidence: {value['confidence']['level']}",
        "",
        "Executed pipeline stages:",
    ]
    lines.extend(f"- {stage}" for stage in value.get("provenance", {}).get("pipeline_stages", []))
    lines.extend(["", "Resolved alert entities:"])
    lines.extend(
        f"- {item['entity_type']}: input={item['input_value']} canonical={item['canonical_value']} method={item['resolution_method']} quality={item['resolution_quality']}"
        for item in value.get("provenance", {}).get("alert_resolved_entities", [])
    )
    lines.extend(["", "Provider query results:"])
    lines.extend(
        f"- {item['provider_id']}: {item['status']} records={item['record_count']} query={item['query_id']}"
        for item in value.get("provenance", {}).get("provider_results", [])
    )
    lines.extend(["", "Candidate selection:"])
    lines.extend(
        f"- SELECTED {item['provider_id']}/{item['record_id']}: {', '.join(item['selection_reasons'])}"
        for item in value.get("provenance", {}).get("selected_candidates", [])
    )
    lines.extend(
        f"- REJECTED {item['record_id']}: {item['reason']}"
        for item in value.get("provenance", {}).get("rejected_candidates", [])
    )
    lines.extend([
        "",
        "Related context:",
    ])
    related = value.get("related_context", [])
    lines.extend(f"- {item['source_provider']}/{item['source_record_id']} [{item['record_type']}] state={item['record_state']}" for item in related)
    if not related:
        lines.append("- None safely supported")
    lines.extend(["", "Correlation results:"])
    lines.extend(
        f"- {item['source_provider']}/{item['context_record_reference']}: {item['relationship_state']} "
        f"({', '.join(feature['feature_type'] + '=' + feature['value'] for feature in item['features'])})"
        for item in value.get("correlation_results", [])
    )
    supporting = value["evidence_set"]["supporting"]
    contradicting = value["evidence_set"]["contradicting"]
    lines.extend(["", f"Supporting evidence: {len(supporting)}"])
    lines.extend(
        f"- SUPPORT {item['evidence_id']} {item['source_provider']}/{item['source_record_id']} "
        f"{item['claim_type']}={item['canonical_values']['feature_value']}"
        for item in supporting
    )
    lines.append(f"Contradicting evidence: {len(contradicting)}")
    lines.extend(
        f"- CONTRADICTION {item['evidence_id']} {item['source_provider']}/{item['source_record_id']} "
        f"{item['claim_type']}={item['canonical_values']['feature_value']}"
        for item in contradicting
    )
    lines.extend(["", "Missing information:"])
    lines.extend(f"- {item}" for item in value.get("missing_information", []))
    if not value.get("missing_information"):
        lines.append("- None")
    lines.extend(["", "Recommended review areas:"])
    lines.extend(f"- {item}" for item in value.get("recommended_review_areas", []))
    if not value.get("recommended_review_areas"):
        lines.append("- None")
    lines.extend(["", "Source provenance:"])
    for item in related:
        provenance = item["provenance"]
        lines.append(
            f"- {item['source_provider']}/{item['source_record_id']}: schema={item['source_schema_version']} "
            f"retrieved={provenance['retrieved_at']} chain={'>'.join(provenance['transformation_chain'])}"
        )
    lines.extend(["", "This packet supplies deterministic context only; analyst judgment remains authoritative."])
    return "\n".join(lines) + "\n"


def _emit(value: str, output: str | None) -> None:
    if output:
        Path(output).write_text(value, encoding="utf-8")
    else:
        print(value, end="")


if __name__ == "__main__":
    raise SystemExit(main())
