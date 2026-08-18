from __future__ import annotations

from conftest import scenario_packet


def _result(packet, record_id):
    return next(item for item in packet.correlation_results if item.context_record_reference == record_id)


def _features(result):
    return {item.feature_type: item.value for item in result.features}


def test_exact_match_features_relationship_and_high_confidence() -> None:
    _, packet = scenario_packet("V01")
    result = _result(packet, "CHG-V01-APPROVED")
    features = _features(result)
    assert result.relationship_state.value == "SUPPORTED"
    assert features["USER_MATCH"] == "EXACT_CANONICAL"
    assert features["HOST_MATCH"] == "NORMALIZED_EQUIVALENT"
    assert features["ACTION_COMPATIBILITY"] == "COMPATIBLE"
    assert features["TEMPORAL_RELATIONSHIP"] == "WITHIN_STRONG_WINDOW"
    assert features["RECORD_STATE"] == "APPROVED"
    assert packet.confidence.level.value == "HIGH"


def test_alias_and_fqdn_semantics_are_explicit() -> None:
    _, alias_packet = scenario_packet("V02")
    _, host_packet = scenario_packet("V03")
    assert _features(_result(alias_packet, "TKT-V02-ALIAS"))["USER_MATCH"] == "EXPLICIT_ALIAS"
    assert alias_packet.confidence.level.value == "MEDIUM"
    assert _features(_result(host_packet, "CHG-V03-FQDN"))["HOST_MATCH"] == "NORMALIZED_EQUIVALENT"


def test_stale_context_is_evaluated_but_not_supported() -> None:
    _, packet = scenario_packet("V07")
    result = _result(packet, "TKT-V07-STALE")
    assert _features(result)["TEMPORAL_RELATIONSHIP"] == "STALE"
    assert result.relationship_state.value == "NOT_SUPPORTED"
    assert packet.confidence.level.value != "HIGH"


def test_cancelled_and_contradictory_actions_create_contradicting_evidence() -> None:
    _, cancelled = scenario_packet("V09")
    _, action = scenario_packet("V10")
    assert _result(cancelled, "CHG-V09-CANCELLED").relationship_state.value == "CONTRADICTED"
    assert any(item.claim_type == "RECORD_STATE" for item in cancelled.evidence_set.contradicting)
    assert _features(_result(action, "ID-V10-CONTRADICT"))["ACTION_COMPATIBILITY"] == "CONTRADICTORY"
    assert any(item.claim_type == "ACTION_COMPATIBILITY" for item in action.evidence_set.contradicting)
    assert action.confidence.level.value == "LOW"


def test_missing_timestamp_is_diagnostic_not_contradiction() -> None:
    _, packet = scenario_packet("V11")
    result = _result(packet, "TKT-V11-NOTIME")
    assert _features(result)["TEMPORAL_RELATIONSHIP"] == "UNKNOWN"
    assert "CONTEXT_TIMESTAMP_MISSING" in {item.code for item in packet.provider_diagnostics}
    assert not any(item.claim_type == "TEMPORAL_RELATIONSHIP" for item in packet.evidence_set.contradicting)
    assert packet.confidence.level.value == "MEDIUM"


def test_historical_case_remains_partial_not_authorization() -> None:
    _, packet = scenario_packet("V14")
    assert _result(packet, "CASE-V14-HISTORY").relationship_state.value == "PARTIALLY_SUPPORTED"
    assert packet.confidence.level.value == "MEDIUM"


def test_identity_conflict_remains_visible_and_reduces_confidence() -> None:
    _, packet = scenario_packet("V19")
    assert packet.execution_status.value == "CONTRADICTORY_CONTEXT"
    assert packet.confidence.level.value == "LOW"
    assert "TKT-V19-SUPPORT" in {item.source_record_id for item in packet.related_context}
    assert any(item.source_record_id == "ID-V19-CONFLICT" for item in packet.evidence_set.contradicting)


def test_evidence_ids_order_and_provenance_are_deterministic() -> None:
    _, left = scenario_packet("V01")
    _, right = scenario_packet("V01")
    left_items = left.evidence_set.supporting + left.evidence_set.contradicting
    right_items = right.evidence_set.supporting + right.evidence_set.contradicting
    assert [item.evidence_id for item in left_items] == [item.evidence_id for item in right_items]
    assert all(item.provenance.source_record_id == item.source_record_id for item in left_items)
    assert len({item.evidence_id for item in left_items}) == len(left_items)
