from context_enrichment.validation.demo_layer import build_demo_layer_report


def test_generated_demo_layer_report_is_execution_derived(repo_root) -> None:
    report = build_demo_layer_report(repo_root, repo_root / "fixtures")
    assert report["check_count"] == 13
    assert report["pass_count"] == 13
    assert report["fail_count"] == 0
    assert report["error_count"] == 0
    assert report["false_association_count"] == 0
    assert report["determinism_result"] == "PASS"
    assert set(report["scenario_results"]) == {"primary", "false-join", "provider-failure"}
    assert all(item["model_adapter_status"] == "DISABLED_NO_MODEL" for item in report["scenario_results"].values())
