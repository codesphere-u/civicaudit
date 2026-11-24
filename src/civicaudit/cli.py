"""CLI and report formatters for civicaudit."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from civicaudit.forensics import AuditReport, audit_ocds_releases


def report_to_json(report: AuditReport) -> str:
    return json.dumps(
        {
            "releases_analyzed": report.releases_analyzed,
            "total_award_value": report.total_award_value,
            "high_risk_flags": report.high_risk_flags,
            "medium_risk_flags": report.medium_risk_flags,
            "benford": {
                "sample_size": report.benford.sample_size,
                "mad": report.benford.mad,
                "chi_squared": report.benford.chi_squared,
                "conformity": report.benford.conformity,
            },
            "flags": [
                {
                    "rule_id": f.rule_id,
                    "severity": f.severity.value,
                    "title": f.title,
                    "buyer": f.buyer,
                    "suppliers": list(f.suppliers),
                    "ocids": list(f.ocids),
                    "detail": f.detail,
                    "metrics": f.metrics,
                }
                for f in report.flags
            ],
            "disclaimer": report.disclaimer,
        },
        indent=2,
    )


def report_to_markdown(report: AuditReport) -> str:
    lines = [
        "# CivicAudit OCDS Procurement Forensics Report",
        "",
        f"- **Releases analyzed:** {report.releases_analyzed}",
        f"- **Total award value:** {report.total_award_value:,.2f}",
        f"- **High-risk flags:** {report.high_risk_flags} | **Medium-risk flags:** {report.medium_risk_flags}",
        f"- **Benford conformity:** `{report.benford.conformity}` "
        f"(n={report.benford.sample_size}, MAD={report.benford.mad})",
        "",
        "## Red Flags",
    ]
    if not report.flags:
        lines.append("- None triggered.")
    else:
        for f in report.flags:
            lines.append(f"- **[{f.severity.value.upper()}] {f.rule_id} — {f.title}**: {f.detail}")
    lines.extend(["", f"> {report.disclaimer}"])
    return "\n".join(lines) + "\n"


def _demo_releases() -> list[dict[str, Any]]:
    return [
        {
            "ocid": "ocds-demo-001",
            "date": "2026-09-02T00:00:00Z",
            "buyer": {"name": "District Works Office"},
            "tender": {
                "procurementMethod": "open",
                "tenderPeriod": {"startDate": "2026-08-29T00:00:00Z", "endDate": "2026-09-01T00:00:00Z"},
                "numberOfTenderers": 1,
                "tenderers": [{"name": "Apex Civil Ltd"}],
            },
            "awards": [
                {
                    "id": "aw-1",
                    "date": "2026-09-02T00:00:00Z",
                    "value": {"amount": 48000},
                    "suppliers": [{"name": "Apex Civil Ltd"}],
                }
            ],
            "contracts": [{"id": "c-1", "awardID": "aw-1", "value": {"amount": 68000}}],
        },
        {
            "ocid": "ocds-demo-002",
            "date": "2026-09-12T00:00:00Z",
            "buyer": {"name": "District Works Office"},
            "tender": {"procurementMethod": "limited", "tenderers": [{"name": "Apex Civil Ltd"}]},
            "awards": [
                {
                    "id": "aw-2",
                    "date": "2026-09-12T00:00:00Z",
                    "value": {"amount": 47500},
                    "suppliers": [{"name": "Apex Civil Ltd"}],
                }
            ],
        },
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="civicaudit",
        description="OCDS 1.1 public procurement red-flag & Benford forensic auditor.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_audit = sub.add_parser("audit", help="Audit an OCDS release package JSON file")
    p_audit.add_argument("ocds_file", help="Path to OCDS JSON (list or {releases: [...]})")
    p_audit.add_argument("--threshold", type=float, default=50_000.0)
    p_audit.add_argument("--format", choices=["markdown", "json"], default="markdown")

    p_demo = sub.add_parser("demo", help="Run forensic audit on a built-in OCDS sample")
    p_demo.add_argument("--format", choices=["markdown", "json"], default="markdown")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "demo":
        rep = audit_ocds_releases(_demo_releases())
        print(report_to_json(rep) if args.format == "json" else report_to_markdown(rep))
        return 0
    if args.command == "audit":
        raw = json.loads(Path(args.ocds_file).read_text(encoding="utf-8"))
        releases = raw["releases"] if isinstance(raw, dict) and "releases" in raw else raw
        rep = audit_ocds_releases(releases, statutory_threshold=args.threshold)
        print(report_to_json(rep) if args.format == "json" else report_to_markdown(rep))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
