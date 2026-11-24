"""civicaudit — OCDS 1.1 public procurement forensic auditor."""

from civicaudit.cli import report_to_json, report_to_markdown
from civicaudit.forensics import (
    BENFORD_CHI2_CRIT_05,
    BENFORD_EXPECTED,
    AuditReport,
    BenfordReport,
    FlagSeverity,
    ProcurementRedFlag,
    audit_ocds_releases,
    evaluate_benford,
)

__version__ = "0.1.0"

__all__ = [
    "BENFORD_CHI2_CRIT_05",
    "BENFORD_EXPECTED",
    "AuditReport",
    "BenfordReport",
    "FlagSeverity",
    "ProcurementRedFlag",
    "__version__",
    "audit_ocds_releases",
    "evaluate_benford",
    "report_to_json",
    "report_to_markdown",
]
