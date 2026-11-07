# Operating runbook

## Local operations

Install Python dependencies, run `python -m pytest -q`, then `insurance-analytics demo`. Verify `summary.json`, the CSV totals and `manifest.json`. Open `report.html` or start the dashboard. API documentation is available at `/docs`. Both services bind to localhost by default; no authentication is implemented in this portfolio service.

Use a clean output directory to reproduce first-run ledger counts. Reusing an output directory intentionally exercises replay protection. Keep the virtual environment, generated artifacts, tracking databases and credentials out of Git. MLflow and Metaflow artifacts may contain serialized Python objects: use trusted storage and matching package versions.

The workflow jobs run with `pip install '.[ml]'`. Set `MLFLOW_TRACKING_URI` as appropriate; local SQLite is the default. A production scheduler should run the monitoring flow after the input snapshot commits and persist its output to controlled storage. The included flow explicitly generates synthetic populations rather than pretending to pull client data.

## Snowflake

1. Create an isolated demo database/schema. Choose a role with create privileges on that schema and permission to execute procedures. No credentials are stored here.
2. Execute `001_schema.sql`, `002_incremental_decisions.sql` and `003_mortality.sql` in order.
3. Load synthetic or approved source data and explicit versioned assumption records. Run every query in `004_quality_checks.sql` as a publishing gate; all must return zero rows. An empty assumption table is also a configuration error and must be rejected by the orchestrator.
4. Run `005_smoke_test.sql` in the demo schema. Both counts should be five. Verify current source version is two. Test a conflicting event in an isolated copy and verify rollback and unchanged stream position.
5. Only after those checks, grant the task owner required managed-task execution permissions and use `ALTER TASK APPLICATION_DELTA_TASK RESUME`. The task is created suspended.

Events must be immutable full snapshots with increasing per-application versions. A late/conflicting event fails the transaction, leaving stream data available for repair and retry. Do not delete a bad row expecting an append-only stream to forget it; suspend the task, inspect the batch, quarantine/repair under an approved recovery process, and re-seed the stream/checkpoint explicitly in an isolated transaction plan. Do not recreate streams during normal deployments, which could lose offsets. Monitor task failures, data freshness and stream staleness. The procedure’s temporary staging DDL precedes its DML transaction to avoid an implicit commit of stream consumption.

For rollback, suspend the task and restore the previous procedure/view definitions. Preserve the append-only source and audit tables. Use versioned assumptions for restatement rather than editing a published historical assumption version.

## AWS and Terraform

Prerequisites: Terraform 1.6+, AWS provider 6.x, an AWS account and region, an existing VPC and private subnets, a same-account ECR repository, and a built image pinned by digest. Private tasks need DNS and HTTPS access to ECR API/Docker, CloudWatch Logs, S3 and other required AWS endpoints via VPC endpoints or NAT. Batch may create its service-linked role; the deployer needs that permission. Supply an encrypted remote Terraform state backend appropriate to your account before team use.

```bash
docker build -t insurance-analytics .
# Scan, tag and push to your same-account ECR repository; obtain the immutable digest.
cd infra
cp terraform.tfvars.example terraform.tfvars
# Fill in the explicit account/network/bucket/image values.
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan -out=reviewed.tfplan
# Inspect the plan, including costs and IAM, before any real deployment.
terraform apply reviewed.tfplan
```

Step Functions submits the Batch job, waits for completion and exposes a failure state. Runtime is bounded by 30 minutes for the job and 35 for the workflow. Batch retries default to one attempt; reruns create a new S3 run prefix. A completed prefix contains `manifest.json`, uploaded last. Compare manifest digests after download. Failed uploads can leave an incomplete prefix with no manifest; ignore it and clean it according to retention policy.

The job role can write only the artifact bucket’s `runs/*` prefix. The execution role can pull only the configured ECR repository and write the configured log group; ECR authorization tokens require wildcard scope. Step Functions' dynamic Batch job monitoring APIs require wildcard resources; submitting jobs is scoped to this queue and job definition. Bucket public access is blocked, versions and encryption are enabled and insecure transport is denied. These controls do not replace an account security review.

The optional ECS dashboard service is private with zero desired tasks and no ingress by default. Remote access needs an authenticated internal gateway/ALB, a dedicated ingress security-group rule and its deployment tests. Scaling it up alone does not make it reachable. No public dashboard or production access is provisioned.

Cost drivers are Fargate task duration, image and artifact storage, logs, NAT/endpoints and Step Functions transitions; Snowflake managed tasks and warehouse queries are separately metered. No live resources were created by building this repository. Stop workloads and scale services to zero when idle. Destroy infrastructure only after preserving required audit artifacts; the versioned non-empty bucket will block accidental deletion.
