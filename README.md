# civicaudit

**Deterministic Open Contracting Data Standard (OCDS 1.1) public procurement forensic auditor: threshold contract-splitting, single-bidder concentration, compressed tender windows, post-award price escalation, co-bidding collusion graphs, and Benford's Law (MAD + Chi-Squared) analysis.**

Zero runtime dependencies. Pure Python 3.11+. Built for auditors-general, anti-corruption commissions, civil-society watchdogs, and investigative journalists.

## Red-Flag Rules

- **`CIVIC-001` Threshold Contract-Splitting:** Rolling-window clusters of awards to the same supplier just below statutory competitive-tender thresholds whose sum exceeds the threshold.
- **`CIVIC-002` Single-Bidder Competitive Award:** Open or selective tenders attracting only one bidder.
- **`CIVIC-003` Compressed Tender Submission Window:** Open tenders closing faster than statutory preparation minimums.
- **`CIVIC-004` Post-Award Price Escalation:** Contract values exceeding original award values beyond configured percentage thresholds.
- **`CIVIC-005` Co-Bidding & Bid-Rotation Ring:** High-Jaccard co-bidding supplier pairs alternating wins across shared tenders.
- **`CIVIC-006` Benford's Law First-Digit Non-Conformity:** Nigrini MAD and Pearson Chi-Squared (`df=8`, `alpha=0.05`) forensic distribution checks.

> **Audit Disclaimer:** Statistical red-flag indicators prioritize human audit investigation and do not constitute legal findings of corruption or wrongdoing.

## Quick Start

```bash
uv sync --extra dev
civicaudit demo --format markdown
civicaudit audit ocds_releases.json --threshold 50000 --format json
```

## License

MIT License — see [LICENSE](LICENSE).
