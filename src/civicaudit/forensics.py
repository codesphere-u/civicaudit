"""Deterministic OCDS 1.1 public procurement forensic detectors & Benford's Law analysis."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

# Theoretical Benford first-digit probabilities P(d) = log10(1 + 1/d)
BENFORD_EXPECTED: dict[int, float] = {d: math.log10(1.0 + 1.0 / d) for d in range(1, 10)}
# Chi-squared critical value for df=8 at alpha=0.05
BENFORD_CHI2_CRIT_05 = 15.507


class FlagSeverity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class ProcurementRedFlag:
    rule_id: str
    severity: FlagSeverity
    title: str
    ocids: tuple[str, ...]
    buyer: str
    suppliers: tuple[str, ...]
    detail: str
    metrics: dict[str, float | int | str]


@dataclass(frozen=True)
class BenfordReport:
    sample_size: int
    observed_counts: dict[int, int]
    observed_proportions: dict[int, float]
    expected_proportions: dict[int, float]
    mad: float  # Nigrini Mean Absolute Deviation
    chi_squared: float
    conformity: str  # close | acceptable | marginal | nonconforming | insufficient_sample


@dataclass(frozen=True)
class AuditReport:
    releases_analyzed: int
    total_award_value: float
    high_risk_flags: int
    medium_risk_flags: int
    benford: BenfordReport
    flags: tuple[ProcurementRedFlag, ...]
    disclaimer: str = (
        "Statistical red-flag indicators prioritize human audit verification and do not "
        "constitute legal findings of corruption or wrongdoing."
    )


def _leading_digit(amount: float) -> int | None:
    if amount <= 0 or not math.isfinite(amount):
        return None
    s = f"{amount:.12e}"
    first = s[0]
    return int(first) if first.isdigit() and first != "0" else None


def evaluate_benford(amounts: list[float], *, min_sample: int = 30) -> BenfordReport:
    """Compute Benford's Law first-digit MAD and Pearson Chi-Squared forensic conformity."""
    counts: dict[int, int] = dict.fromkeys(range(1, 10), 0)
    valid_n = 0
    for amt in amounts:
        d = _leading_digit(amt)
        if d is not None:
            counts[d] += 1
            valid_n += 1

    if valid_n < min_sample:
        props = {d: (round(counts[d] / valid_n, 4) if valid_n else 0.0) for d in range(1, 10)}
        return BenfordReport(
            sample_size=valid_n,
            observed_counts=counts,
            observed_proportions=props,
            expected_proportions={d: round(p, 4) for d, p in BENFORD_EXPECTED.items()},
            mad=0.0,
            chi_squared=0.0,
            conformity="insufficient_sample",
        )

    obs_props: dict[int, float] = {}
    mad_sum = 0.0
    chi2 = 0.0
    for d in range(1, 10):
        obs_p = counts[d] / valid_n
        exp_p = BENFORD_EXPECTED[d]
        exp_c = exp_p * valid_n
        obs_props[d] = round(obs_p, 4)
        mad_sum += abs(obs_p - exp_p)
        chi2 += ((counts[d] - exp_c) ** 2) / exp_c

    mad = round(mad_sum / 9.0, 5)
    chi2 = round(chi2, 3)

    if mad <= 0.006:
        conformity = "close"
    elif mad <= 0.012:
        conformity = "acceptable"
    elif mad <= 0.015:
        conformity = "marginal"
    else:
        conformity = "nonconforming"

    return BenfordReport(
        sample_size=valid_n,
        observed_counts=counts,
        observed_proportions=obs_props,
        expected_proportions={d: round(p, 4) for d, p in BENFORD_EXPECTED.items()},
        mad=mad,
        chi_squared=chi2,
        conformity=conformity,
    )


def _parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def audit_ocds_releases(
    releases: list[dict[str, Any]],
    *,
    statutory_threshold: float = 50_000.0,
    splitting_window_days: int = 30,
    min_open_tender_days: int = 7,
    escalation_pct_threshold: float = 0.25,
    collusion_min_co_bids: int = 3,
    collusion_jaccard_threshold: float = 0.65,
) -> AuditReport:
    """Run all 6 deterministic OCDS forensic detectors across a list of OCDS 1.1 releases."""
    flags: list[ProcurementRedFlag] = []
    award_amounts: list[float] = []
    # (buyer, supplier) -> list[(award_date, amount, ocid)]
    buyer_supplier_awards: dict[tuple[str, str], list[tuple[datetime, float, str]]] = defaultdict(list)
    # bidder -> set of ocids bid on
    bidder_tenders: dict[str, set[str]] = defaultdict(set)
    # ocid -> winner supplier names
    tender_winners: dict[str, set[str]] = defaultdict(set)

    for rel in releases:
        ocid = str(rel.get("ocid") or rel.get("id") or "unknown")
        buyer = str((rel.get("buyer") or {}).get("name") or "Unknown Buyer")
        tender = rel.get("tender") or {}
        method = str(tender.get("procurementMethod") or "").lower()
        t_period = tender.get("tenderPeriod") or {}
        t_start = _parse_iso(t_period.get("startDate"))
        t_end = _parse_iso(t_period.get("endDate"))

        # CIVIC-003: Compressed tender window on open tenders
        if method == "open" and t_start and t_end:
            window_days = (t_end - t_start).total_seconds() / 86_400.0
            if 0.0 <= window_days < min_open_tender_days:
                flags.append(
                    ProcurementRedFlag(
                        rule_id="CIVIC-003",
                        severity=FlagSeverity.MEDIUM,
                        title="Compressed Open-Tender Submission Window",
                        ocids=(ocid,),
                        buyer=buyer,
                        suppliers=(),
                        detail=(
                            f"Open tender {ocid} allowed only {window_days:.1f} days "
                            f"(< {min_open_tender_days}-day minimum)."
                        ),
                        metrics={"window_days": round(window_days, 2), "min_days": min_open_tender_days},
                    )
                )

        # Bidders list (OCDS tender.tenderers or bids.details)
        tenderers = [str(t.get("name") or t.get("id") or "") for t in (tender.get("tenderers") or [])]
        tenderers = [t for t in tenderers if t]
        num_tenderers = tender.get("numberOfTenderers")
        bidder_count = int(num_tenderers) if isinstance(num_tenderers, int) else len(tenderers)

        for bidder in set(tenderers):
            bidder_tenders[bidder].add(ocid)

        awards = rel.get("awards") or []
        award_totals_by_id: dict[str, float] = {}
        for aw in awards:
            aw_id = str(aw.get("id") or ocid)
            val = aw.get("value") or {}
            amt = float(val.get("amount") or 0.0)
            if amt > 0:
                award_amounts.append(amt)
                award_totals_by_id[aw_id] = amt

            suppliers = [str(s.get("name") or s.get("id") or "Unknown") for s in (aw.get("suppliers") or [])]
            for sup in suppliers:
                tender_winners[ocid].add(sup)
            aw_date = _parse_iso(aw.get("date")) or _parse_iso(rel.get("date"))
            if aw_date and amt > 0:
                for sup in suppliers:
                    buyer_supplier_awards[(buyer, sup)].append((aw_date, amt, ocid))

            # CIVIC-002: Single-bidder award on competitive tender
            if method in ("open", "selective") and bidder_count == 1:
                flags.append(
                    ProcurementRedFlag(
                        rule_id="CIVIC-002",
                        severity=FlagSeverity.HIGH,
                        title="Single-Bidder Competitive Tender Award",
                        ocids=(ocid,),
                        buyer=buyer,
                        suppliers=tuple(suppliers),
                        detail=f"Competitive ({method}) tender {ocid} received only 1 bid (amount={amt:,.2f}).",
                        metrics={"amount": amt, "bidder_count": 1},
                    )
                )

        # CIVIC-004: Post-award contract price escalation creep
        for contract in rel.get("contracts") or []:
            c_amt = float((contract.get("value") or {}).get("amount") or 0.0)
            aw_ref = str(contract.get("awardID") or ocid)
            orig_amt = award_totals_by_id.get(aw_ref)
            if orig_amt and orig_amt > 0 and c_amt > orig_amt:
                pct = (c_amt - orig_amt) / orig_amt
                if pct >= escalation_pct_threshold:
                    flags.append(
                        ProcurementRedFlag(
                            rule_id="CIVIC-004",
                            severity=FlagSeverity.HIGH,
                            title="Post-Award Contract Price Escalation",
                            ocids=(ocid,),
                            buyer=buyer,
                            suppliers=tuple(sorted(tender_winners.get(ocid, set()))),
                            detail=(
                                f"Contract value ({c_amt:,.2f}) exceeded award ({orig_amt:,.2f}) "
                                f"by {pct * 100:.1f}%."
                            ),
                            metrics={
                                "award_amount": orig_amt,
                                "contract_amount": c_amt,
                                "escalation_pct": round(pct * 100.0, 2),
                            },
                        )
                    )

    # CIVIC-001: Threshold contract-splitting within rolling window
    lower_band = statutory_threshold * 0.65
    for (buyer, supplier), items in buyer_supplier_awards.items():
        just_below = sorted(
            [(dt, amt, ocid) for dt, amt, ocid in items if lower_band <= amt < statutory_threshold],
            key=lambda x: x[0],
        )
        i = 0
        while i < len(just_below):
            start_dt = just_below[i][0]
            cluster = [just_below[i]]
            j = i + 1
            while j < len(just_below) and (just_below[j][0] - start_dt).days <= splitting_window_days:
                cluster.append(just_below[j])
                j += 1
            cluster_sum = sum(x[1] for x in cluster)
            if len(cluster) >= 2 and cluster_sum >= statutory_threshold:
                flags.append(
                    ProcurementRedFlag(
                        rule_id="CIVIC-001",
                        severity=FlagSeverity.HIGH,
                        title="Threshold Contract-Splitting Pattern",
                        ocids=tuple(x[2] for x in cluster),
                        buyer=buyer,
                        suppliers=(supplier,),
                        detail=(
                            f"{len(cluster)} awards to '{supplier}' within {splitting_window_days}d "
                            f"each sit below {statutory_threshold:,.0f} but total {cluster_sum:,.2f}."
                        ),
                        metrics={
                            "contract_count": len(cluster),
                            "combined_value": round(cluster_sum, 2),
                            "statutory_threshold": statutory_threshold,
                        },
                    )
                )
                i = j
            else:
                i += 1

    # CIVIC-005: Co-bidding / bid-rotation collusion graph
    bidders = sorted(bidder_tenders.keys())
    for i in range(len(bidders)):
        b1 = bidders[i]
        t1 = bidder_tenders[b1]
        if len(t1) < collusion_min_co_bids:
            continue
        for j in range(i + 1, len(bidders)):
            b2 = bidders[j]
            t2 = bidder_tenders[b2]
            shared = t1 & t2
            if len(shared) < collusion_min_co_bids:
                continue
            jaccard = len(shared) / len(t1 | t2)
            if jaccard >= collusion_jaccard_threshold:
                b1_wins = sum(1 for o in shared if b1 in tender_winners.get(o, set()))
                b2_wins = sum(1 for o in shared if b2 in tender_winners.get(o, set()))
                if b1_wins >= 1 and b2_wins >= 1:
                    flags.append(
                        ProcurementRedFlag(
                            rule_id="CIVIC-005",
                            severity=FlagSeverity.HIGH,
                            title="Co-Bidding & Alternating-Win Collusion Pair",
                            ocids=tuple(sorted(shared)),
                            buyer="Multiple / Shared Tenders",
                            suppliers=(b1, b2),
                            detail=(
                                f"'{b1}' and '{b2}' co-bid on {len(shared)} tenders "
                                f"(Jaccard={jaccard:.2f}) and alternated wins ({b1_wins} vs {b2_wins})."
                            ),
                            metrics={
                                "shared_tenders": len(shared),
                                "jaccard": round(jaccard, 3),
                                "wins_a": b1_wins,
                                "wins_b": b2_wins,
                            },
                        )
                    )

    # CIVIC-006: Benford's Law conformity check
    benford = evaluate_benford(award_amounts)
    if benford.conformity == "nonconforming" or benford.chi_squared > BENFORD_CHI2_CRIT_05:
        flags.append(
            ProcurementRedFlag(
                rule_id="CIVIC-006",
                severity=FlagSeverity.MEDIUM,
                title="Benford's Law First-Digit Non-Conformity",
                ocids=(),
                buyer="Dataset-Wide",
                suppliers=(),
                detail=(
                    f"Award values (n={benford.sample_size}) deviate from Benford's Law "
                    f"(MAD={benford.mad:.4f}, chi2={benford.chi_squared:.2f}, status={benford.conformity})."
                ),
                metrics={
                    "sample_size": benford.sample_size,
                    "mad": benford.mad,
                    "chi_squared": benford.chi_squared,
                },
            )
        )

    high_count = sum(1 for f in flags if f.severity == FlagSeverity.HIGH)
    med_count = sum(1 for f in flags if f.severity == FlagSeverity.MEDIUM)
    return AuditReport(
        releases_analyzed=len(releases),
        total_award_value=round(sum(award_amounts), 2),
        high_risk_flags=high_count,
        medium_risk_flags=med_count,
        benford=benford,
        flags=tuple(flags),
    )
