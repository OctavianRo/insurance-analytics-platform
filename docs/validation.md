# Validation record

Validated locally on 7 November 2026 with Python 3.13.1 on macOS arm64.

| Check | Observed result |
|---|---|
| Automated domain/API/dashboard tests | **32 passed** |
| Ruff lint and formatting | Passed for package, tests and workflow adapters |
| Full logistic demo | Completed; temporal holdout AUC 0.8088; 600 holdout applications |
| Full XGBoost demo | Completed; temporal holdout AUC 0.7813; 600 holdout applications |
| Replayed full demos | No new decision deltas; existing ledger preserved |
| Artifact integrity | Every declared SHA-256 digest matched its generated file |
| Metaflow underwriting, logistic | start / fit / end completed; MLflow run and model artifact recorded |
| Metaflow underwriting, XGBoost | start / fit / end completed; MLflow run and model artifact recorded |
| Metaflow monitoring | start / report / end completed; Evidently HTML and drift CSV created |
| Dependency consistency | `pip check` passed after pandas/Plotly compatibility constraints |
| Terraform 1.14.0 + AWS provider 6.72.0 | Recursive format check and `terraform validate` passed |
| Browser dashboard check | Mortality chart rendered; multiplier 1.0→1.2 changed expected deaths 18.4→22.1 and A/E 1.03→0.86; monitoring and reporting tabs rendered |
| Concurrent chart callbacks | Regression test passed after serializing Plotly template initialization |

Synthetic metrics are demonstrations of software behavior and do not validate a model for real insurance applications. Sample summaries in `examples/` include the persistent ledger's replay count and are not promises of operational model quality.

External dependencies emitted deprecation notices for the FastAPI/Starlette HTTP test client and Dash DataTable; they did not fail the tests. Metaflow emitted a Python gzip cleanup warning during packaging, while all steps completed successfully. No runtime warning was suppressed to obtain a passing result.

## Checks requiring external environments

- Snowflake SQL is supplied with quality gates and a smoke-test script, but was **not executed against a Snowflake account**.
- AWS infrastructure was **not applied**; IAM behavior, networking, container pulls, Step Functions/Batch execution and artifact uploads still need live integration verification.
- A Docker daemon was not available locally. The GitHub Actions container job builds the image and runs the complete demo inside it.
- The committed dependency snapshots describe the tested Python 3.13 environment. The CI Python version matrix validates supported dependency resolution on Linux separately.

CI definitions cover lint, formatting, domain tests, both demo backends, Terraform format/validation, Docker build/smoke execution, and both workflow integrations. Check the actual GitHub Actions run for remote execution results.
