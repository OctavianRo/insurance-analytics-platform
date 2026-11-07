data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
locals {
  prefix             = "arn:${data.aws_partition.current.partition}"
  account            = data.aws_caller_identity.current.account_id
  ecr_repository_arn = "${local.prefix}:ecr:${var.region}:${local.account}:repository/${split("@", join("/", slice(split("/", var.image_uri), 1, length(split("/", var.image_uri)))))[0]}"
}
resource "aws_s3_bucket" "artifacts" { bucket = var.artifact_bucket_name }
resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_policy" "tls" {
  bucket = aws_s3_bucket.artifacts.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Deny", Principal = "*", Action = "s3:*",
    Resource  = [aws_s3_bucket.artifacts.arn, "${aws_s3_bucket.artifacts.arn}/*"],
    Condition = { Bool = { "aws:SecureTransport" = "false" } }
  }] })
}
resource "aws_cloudwatch_log_group" "runtime" {
  name              = "/analytics/${var.name}"
  retention_in_days = 30
}
resource "aws_security_group" "runtime" {
  name_prefix = "${var.name}-"
  description = "Private analytics tasks, no inbound traffic"
  vpc_id      = var.vpc_id
  egress {
    description = "HTTPS to AWS endpoints via VPC endpoints or NAT"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_iam_role" "execution" {
  name_prefix = "${var.name}-exec-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow",
  Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy" "execution" {
  role = aws_iam_role.execution.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], Resource = local.ecr_repository_arn },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.runtime.arn}:*" }
  ] })
}
resource "aws_iam_role" "job" {
  name_prefix        = "${var.name}-job-"
  assume_role_policy = aws_iam_role.execution.assume_role_policy
}
resource "aws_iam_role_policy" "job" {
  role = aws_iam_role.job.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow",
  Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.artifacts.arn}/runs/*" }] })
}
resource "aws_batch_compute_environment" "fargate" {
  name_prefix = "${var.name}-"
  type        = "MANAGED"
  compute_resources {
    type               = "FARGATE"
    max_vcpus          = 4
    subnets            = var.private_subnet_ids
    security_group_ids = [aws_security_group.runtime.id]
  }
}
resource "aws_batch_job_queue" "analytics" {
  name     = var.name
  state    = "ENABLED"
  priority = 1
  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.fargate.arn
  }
}
resource "aws_batch_job_definition" "analytics" {
  name                  = var.name
  type                  = "container"
  platform_capabilities = ["FARGATE"]
  timeout { attempt_duration_seconds = 1800 }
  retry_strategy { attempts = 1 }
  container_properties = jsonencode({
    image                = var.image_uri, command = ["python", "-m", "insurance_analytics.cloud"],
    executionRoleArn     = aws_iam_role.execution.arn, jobRoleArn = aws_iam_role.job.arn,
    resourceRequirements = [{ type = "VCPU", value = "1" }, { type = "MEMORY", value = "2048" }],
    networkConfiguration = { assignPublicIp = "DISABLED" },
    environment          = [{ name = "ARTIFACT_BUCKET", value = aws_s3_bucket.artifacts.id }],
    logConfiguration = { logDriver = "awslogs", options = {
      "awslogs-group"  = aws_cloudwatch_log_group.runtime.name,
      "awslogs-region" = var.region, "awslogs-stream-prefix" = "batch"
    } }
  })
}
resource "aws_iam_role" "states" {
  name_prefix = "${var.name}-states-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow",
  Principal = { Service = "states.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy" "states" {
  role = aws_iam_role.states.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["batch:SubmitJob"], Resource = [aws_batch_job_queue.analytics.arn, aws_batch_job_definition.analytics.arn] },
    { Effect = "Allow", Action = ["batch:DescribeJobs", "batch:TerminateJob"], Resource = "*" },
    { Effect = "Allow", Action = ["events:PutTargets", "events:PutRule", "events:DescribeRule"], Resource = "${local.prefix}:events:${var.region}:${local.account}:rule/StepFunctionsGetEventsForBatchJobsRule" }
  ] })
}
resource "aws_sfn_state_machine" "analytics" {
  name     = var.name
  role_arn = aws_iam_role.states.arn
  definition = jsonencode({ StartAt = "Analytics", TimeoutSeconds = 2100, States = {
    Analytics = { Type = "Task", Resource = "${local.prefix}:states:::batch:submitJob.sync",
      Parameters = { JobName = var.name, JobQueue = aws_batch_job_queue.analytics.arn,
      JobDefinition = aws_batch_job_definition.analytics.arn },
    Catch = [{ ErrorEquals = ["States.ALL"], Next = "Failed", ResultPath = "$.error" }], End = true },
    Failed = { Type = "Fail", Error = "AnalyticsJobFailed" }
  } })
  depends_on = [aws_iam_role_policy.states]
}
resource "aws_ecs_cluster" "analytics" { name = var.name }
resource "aws_ecs_task_definition" "dashboard" {
  family                   = "${var.name}-dashboard"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn
  container_definitions = jsonencode([{
    name         = "dashboard", image = var.image_uri, essential = true,
    command      = ["insurance-analytics", "dashboard", "--host", "0.0.0.0"],
    portMappings = [{ containerPort = 8050, protocol = "tcp" }],
    logConfiguration = { logDriver = "awslogs", options = {
      "awslogs-group"         = aws_cloudwatch_log_group.runtime.name, "awslogs-region" = var.region,
      "awslogs-stream-prefix" = "dashboard"
    } }
  }])
}
resource "aws_ecs_service" "dashboard" {
  name            = "${var.name}-dashboard"
  cluster         = aws_ecs_cluster.analytics.id
  task_definition = aws_ecs_task_definition.dashboard.arn
  desired_count   = var.dashboard_desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.runtime.id]
    assign_public_ip = false
  }
}
output "state_machine_arn" { value = aws_sfn_state_machine.analytics.arn }
output "cluster_arn" { value = aws_ecs_cluster.analytics.arn }
