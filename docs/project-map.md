# Acceptance criteria and extension points

| Capability | Acceptance evidence | Next integration boundary |
|---|---|---|
| Underwriting ML | Temporal holdout isolation; probability bounds; signal above chance; unknown category and missing lab handling; both backends run | Approved applicant/label adapter; person-level split; external validation |
| Mortality analytics | Group totals reconcile; hand-calculated APV; zero-death uncertainty; assumption monotonicity | Licensed assumption tables; policy episode exposure; treaty cash flows |
| Incremental decisions | Idempotent replay; conflict/stale rollback; null clearing; multiple warehouse versions | Source ordering and event retention; live Snowflake smoke tests |
| Model monitoring | Identical/shifted/constant PSI; missing-data alert; immature labels excluded | Registry version tags; scheduled ingestion; alert destination |
| RFP preparation | Date boundaries; accepted + rejected = input; bad-date quarantine; SHA-256 fingerprint | Client-specific mapping and episode handling |
| Premium reports | Half-cent rounding; negative reversals; snapshot volume; currency separation | Accounting ledger reconciliation and treaty configuration |
| Survival | Simulated risk direction recovered; decreasing survival; tied-time and no-event behavior | PH diagnostics; uncertainty; efficient risk-set implementation |
| Differential detector | Disjoint policy cohorts; exact holdout totals; corrected tests; bounded credibility | Prospective confirmation and assumption governance |
| Embeddings | Strong categorical rate contrast learned; loss falls; unknown levels finite | Hierarchical priors; validation and age/duration smoothing constraints |
| Cause of death | Unknowns preserved; low counts suppressed | Complete ICD hierarchy; population denominators; disclosure review |
| Cloud execution | Terraform format/validate; container and CI definitions | Live AWS deploy/run/cleanup with account-specific credentials |

The business roadmap should prioritize validated study preparation and reporting first, then analytical models, followed by monitored deployment. Adoption, turnaround time and analyst reconciliation effort are appropriate operational measures. No invented business benefit percentages are included.
