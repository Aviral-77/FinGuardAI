"""Composer, PDF and the ML/LLM config switches."""

from __future__ import annotations

from app.analysis import run_analysis
from app.copilot import llm
from app.copilot.composer import compose_narrative
from app.copilot.templates import build_case
from app.dataio import load_dataset
from app.report.pdf import build_report_pdf, case_reference


def _analysis():
    return run_analysis(load_dataset(), ml_enabled=False)


def test_composer_orders_by_points_and_closes_with_classification():
    analysis = _analysis()
    hub = analysis.scores["ACC-R001"]
    text = compose_narrative("ACC-R001", hub.hits)
    assert text.startswith("Account ACC-R001")
    # Highest-points rule (G3, +35) leads the sentence.
    assert "cluster" in text.split(".")[0]
    assert text.rstrip().endswith(".")
    assert "mule network" in text or "mule account" in text


def test_composer_treats_the_victim_as_a_victim():
    analysis = _analysis()
    victim = analysis.scores["ACC-V001"]
    text = compose_narrative("ACC-V001", victim.hits, is_victim=True)
    assert "victim" in text.lower()
    assert "participant" in text.lower()


def test_composer_handles_no_hits():
    text = compose_narrative("ACC-NEW", [])
    assert "no detection rule" in text


def test_llm_defaults_to_composer_without_a_provider():
    assert llm.active_provider() == "none"
    case = build_case(_analysis(), "ACC-R001")
    text, source = llm.narrate(case)
    assert source == "composer"
    assert text == case["summary"]


def test_ml_flag_toggles_the_anomaly_layer():
    off = run_analysis(load_dataset(), ml_enabled=False)
    on = run_analysis(load_dataset(), ml_enabled=True)
    assert off.networks == []
    assert len(off.anomaly.findings) == 0
    # With ML on, the stealth ring the rules miss reappears.
    assert len(on.networks) >= 1
    assert any(n.missed_by_rules for n in on.networks)


def test_case_reference_is_stable():
    assert case_reference("ACC-R001", "2026-05-30T22:15:00") == case_reference(
        "ACC-R001", "2026-05-30T09:00:00"
    )


def test_pdf_builds_from_a_case():
    analysis = _analysis()
    case = build_case(analysis, "ACC-R001")
    pdf = build_report_pdf(case, analysis, ring={"accounts": ["ACC-R001"], "count": 1, "value_in_motion": 100.0})
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 2000
