"""Tests for OCDS procurement red-flag detectors, Benford's Law, collusion graphs, and CLI."""

from __future__ import annotations

import json
import math
from pathlib import Path

from civicaudit import audit_ocds_releases, evaluate_benford, report_to_json, report_to_markdown
from civicaudit.cli import main as cli_main


def test_benford_accepts_geometric_distribution_and_flags_fabricated_numbers() -> None:
    benford_series = [10.0 ** (i / 100.0) for i in range(300)]
    clean = evaluate_benford(benford_series)
    assert clean.conformity in ("close", "acceptable")
    assert clean.chi_squared < 15.507

    fabricated = [49_500.0] * 40 + [98_000.0] * 20
    suspicious = evaluate_benford(fabricated)
    assert suspicious.conformity == "nonconforming"
    assert suspicious.mad > 0.015
    assert suspicious.chi_squared > 15.507


def test_detects_contract_splitting_single_bidder_short_window_and_escalation() -> None:
    releases = [
        {
            "ocid": "ocds-001",
            "date": "2026-09-01T00:00:00Z",
            "buyer": {"name": "Ministry of Works"},
            "tender": {
                "procurementMethod": "open",
                "tenderPeriod": {"startDate": "2026-08-29T00:00:00Z", "endDate": "2026-09-01T00:00:00Z"},
                "numberOfTenderers": 1,
                "tenderers": [{"name": "Omega Builders"}],
            },
            "awards": [
                {
                    "id": "a1",
                    "date": "2026-09-01T00:00:00Z",
                    "value": {"amount": 48_000},
                    "suppliers": [{"name": "Omega Builders"}],
                }
            ],
            "contracts": [{"id": "c1", "awardID": "a1", "value": {"amount": 65_000}}],
        },
        {
            "ocid": "ocds-002",
            "date": "2026-09-10T00:00:00Z",
            "buyer": {"name": "Ministry of Works"},
            "tender": {"procurementMethod": "limited", "tenderers": [{"name": "Omega Builders"}]},
            "awards": [
                {
                    "id": "a2",
                    "date": "2026-09-10T00:00:00Z",
                    "value": {"amount": 46_000},
                    "suppliers": [{"name": "Omega Builders"}],
                }
            ],
        },
    ]
    rep = audit_ocds_releases(releases, statutory_threshold=50_000.0)
    rules = {f.rule_id for f in rep.flags}
    assert {"CIVIC-001", "CIVIC-002", "CIVIC-003", "CIVIC-004"}.issubset(rules)
    assert "do not" in rep.disclaimer.lower()
    assert json.loads(report_to_json(rep))["high_risk_flags"] >= 3
    assert "CivicAudit" in report_to_markdown(rep)


def test_detects_co_bidding_alternating_win_collusion_ring() -> None:
    releases = []
    for idx in range(4):
        winner = "Firm A" if idx % 2 == 0 else "Firm B"
        releases.append(
            {
                "ocid": f"ocds-ring-{idx}",
                "date": f"2026-0{idx + 1}-10T00:00:00Z",
                "buyer": {"name": "City Roads Authority"},
                "tender": {
                    "procurementMethod": "open",
                    "tenderers": [{"name": "Firm A"}, {"name": "Firm B"}],
                },
                "awards": [{"id": f"aw-{idx}", "value": {"amount": 120_000}, "suppliers": [{"name": winner}]}],
            }
        )
    rep = audit_ocds_releases(releases)
    assert any(f.rule_id == "CIVIC-005" for f in rep.flags)
    assert math.isfinite(rep.total_award_value)


def test_cli_demo_and_file_audit(tmp_path: Path) -> None:
    assert cli_main(["demo", "--format", "json"]) == 0
    assert cli_main(["demo", "--format", "markdown"]) == 0
    ocds_file = tmp_path / "pkg.json"
    ocds_file.write_text(json.dumps({"releases": []}), encoding="utf-8")
    assert cli_main(["audit", str(ocds_file), "--format", "json"]) == 0
