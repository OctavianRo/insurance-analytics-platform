# Methods and limitations

## Underwriting and acceleration

Applications are sorted by application timestamp. The first 80% forms development data and the final 20% is untouched holdout; all records sharing the cutoff timestamp stay in holdout. Synthetic applications have one record per applicant. Real repeated applicants require person-level isolation before splitting. Sigmoid calibration uses three stratified folds strictly inside development, with every fold fitting its own preprocessing pipeline. Neither targets, identifiers nor timestamps are predictors.

The model reports ROC AUC, average precision, prevalence and Brier loss. These are synthetic diagnostics, not estimates of real-world performance. Logistic regression is the default interpretable baseline. XGBoost is an optional small nonlinear comparator with a fixed seed and single-thread execution. There is no automated model promotion.

Acceleration uses a separately generated `requires_full_review` outcome. A fixed illustrative threshold identifies candidate referrals and reports the proportion of candidates that still needed review. Threshold tuning requires a separate validation cohort and a business-approved error budget. No production eligibility decisions are made.

## Mortality and APV

Exposure is measured in years. `expected_rate` is an annual force of mortality (hazard), not an annual death probability. Expected deaths are exposure × hazard × assumption multiplier × annual improvement factor. Count A/E is total deaths / total expected deaths; amount A/E weights deaths and expectations by sum assured. Exact count intervals assume Poisson deaths and fixed expectations. Amount-weighted uncertainty is not represented by count intervals. A/E is undefined when expected deaths are zero and remains missing.

Improvement is compounded relative to an explicit base year and assumption version. No actual pricing table is included. The synthetic generator samples exponential death times and stops exposure at death or censoring. Sparse data can produce large or unstable A/E ratios, which the confidence intervals make visible.

APV uses conditional annual qx, beginning-of-year survival, and end-of-year benefit discounting. No surrender, premium, expense, tax, joint-life or reinsurance treaty cash flows are modeled. Snowflake’s APV view supports a varying annual interest rate; Python uses a constant rate. qx = 1 causes subsequent survival to be zero.

## Survival

The Cox implementation uses right-censored observations, standardized covariates, L2-penalized partial likelihood, Breslow handling of tied death times, and a Breslow baseline cumulative hazard. Standardization and coefficients are fit on development data only. Predictions return stepwise survival from the observed baseline. Survival beyond the observed event horizon is flat and is not a justified long-term projection.

Risk sets are explicit and favor reviewability over large-cohort efficiency. The implementation is suitable for demonstrations and small studies; a validated survival library and proportional-hazards diagnostics are needed for large production studies. Concordance excludes tied event times and compares an observed event only with strictly later durations. No variance estimate or censoring-adjusted time-dependent AUC is claimed.

## Differential discovery

CART fits observed/expected ratios weighted by expected deaths on discovery data. Leaf definitions are fixed before evaluating disjoint holdout policies. Holdout reports exact Poisson intervals, a conservative two-tail Poisson p-value, and Benjamini–Hochberg adjusted q-values across leaves. Limited-fluctuation full credibility is `(z / relative_error)^2`; partial credibility is `min(1, sqrt(actual/full))`. A review flag needs full credibility and an adjusted significance result. It is reasonable for the small synthetic study to generate no flags. Actuarial judgment and independent confirmation are still required; thresholds do not establish a recommended assumption change.

## Embeddings

Each categorical variable has a learned vector. Concatenated vectors pass through a tanh hidden layer; the scalar output adjusts a supplied positive expected-deaths offset on the log scale. Full-batch gradient descent minimizes Poisson negative log likelihood (up to the count-factorial constant). Code computes actual gradients for both embedding tables and network weights; tests require recovery of a deliberately strong category signal. Unknown categories use an untrained zero vector. The synthetic table is already close to its generating assumptions, so its model improvement can be tiny. This is not a validated sparse-mortality smoothing method; regularization, cross-validation and calibration across age/duration cells are needed before assumption setting.

## Monitoring

PSI bins are determined from reference quantiles, with open tails and additive 0.5 smoothing; constant reference features receive a narrow central bin. Missingness is monitored separately. KS p-values are adjusted across features. An alert fires for PSI ≥ 0.2, adjusted p < 0.05, a missingness change > 0.1 or no finite observations. These are illustrative rules: sample size and business relevance affect interpretation. Drift does not prove performance degradation. Delayed-performance joins unique predictions and labels, using only predictions scored and labels available on or before the reporting cutoff.

## Studies and reporting

Study windows are [start, end), with ACT/365.25 exposure. Each input row is accepted or quarantined with reasons. Zero-exposure policies remain visible with an `in_study` flag. This adapter expects a single continuous coverage period per policy; reinstatements and multiple episodes require episode keys and interval normalization. Boundary death conventions must be agreed for real studies.

Premiums are converted to integer cents with Decimal ROUND_HALF_UP before applying ceded shares. Reversals retain their sign. Currency totals never mix. Monthly volume is the final transaction snapshot for each policy/client/currency, not a sum of repeated premium-event face amounts. This assumes each record includes the complete current face amount and share. Treaty terms, earned premium, FX and accounting reconciliation need separate real-world specifications.

Cause-of-death grouping covers a few ICD-10 chapters plus an explicit residual/unknown group. It is not a complete CDC cause hierarchy or an age-standardized mortality study. Simple cell suppression is used without complementary totals in that output; a publication with overlapping tables needs a full disclosure-control policy.
