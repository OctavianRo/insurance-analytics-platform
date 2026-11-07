# Architecture decisions

One installable Python package implements shared domain operations; CLI jobs, FastAPI, Dash and workflow adapters call those operations. This reduces disagreement between interactive reports and scheduled calculations. Heavy integrations are optional so the local demo runs without accounts or credentials.

Data contracts check required fields, key uniqueness, finite values and domain ranges. Invalid study records are quarantined; structurally invalid datasets or conflicting events fail explicitly. Production adapters should emit the same contracts and preserve source versions and immutable ingestion identifiers.

The SQLite decision store uses an immediate write transaction to serialize concurrent writers and commits event registration, field deltas and latest state together. It rejects out-of-order versions rather than silently overwriting newer state. It supports patch semantics, including explicit null clearing. Snowflake uses complete-snapshot events and handles multiple increasing versions in one stream batch with a prior-state window. Those contracts are intentionally documented separately. A Snowflake stream can collapse intermediate updates to mutable source rows, so the warehouse input is an append-only immutable event table.

Demo artifacts include data fingerprints, package versions, held-out predictions and metrics. They can be traced to a seed and input schema. HTML chart IDs are generated at runtime; the report hash can change between runs even when the numeric results agree. Replay counts also depend on the existing audit ledger. They are operational facts, not evidence that a model changed.

The API binds to localhost by default. It generates its named synthetic model once per process. A production model service should load a reviewed, signed/allowlisted artifact from a registry at startup, enforce a versioned feature schema, expose readiness and provenance, and require authentication at its gateway. Record-level medical fields should never be placed in request logs.

AWS orchestration uses Step Functions' synchronous Batch integration, Fargate compute capped at four vCPUs, and per-run S3 prefixes. A manifest is uploaded after all files to mark completion. A retry produces a new prefix, avoiding overwriting an earlier run; downstream consumers must consume only prefixes with a manifest. This is isolated execution, not exactly-once cloud job processing.

The Snowflake scripts and AWS module are reference integration implementations. Account-specific roles, networking, retention, audit requirements, alerts and deployment checks remain the deployer’s responsibility. Nothing runs against a real insurer or policyholder.

Dependency compatibility is deliberate: pandas 2.x and Plotly 5.24 are shared with the tested Evidently integration. Dash callbacks serialize chart creation because Plotly 5 lazily mutates shared template objects; a concurrent callback regression test covers this boundary.
