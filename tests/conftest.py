from __future__ import annotations

from pathlib import Path

import pytest

from context_enrichment.application.service import EnrichmentService
from context_enrichment.providers.mock import build_mock_providers
from context_enrichment.validation.harness import load_scenario


REPOSITORY = Path(__file__).resolve().parents[1]
SCENARIOS = REPOSITORY / "fixtures" / "scenarios"


def scenario_packet(scenario_id: str):
    scenario = load_scenario(SCENARIOS / f"{scenario_id}.json")
    service = EnrichmentService(providers=build_mock_providers(scenario.provider_records, scenario.provider_status))
    return scenario, service.enrich(scenario.alert)


@pytest.fixture
def repo_root() -> Path:
    return REPOSITORY
