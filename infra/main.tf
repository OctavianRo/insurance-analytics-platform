variable "region" {
  type    = string
  default = "eu-west-1"
}
variable "name" {
  type    = string
  default = "insurance-analytics"
}
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "image_uri" {
  type        = string
  description = "ECR image pinned by @sha256 digest; built and scanned separately."
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.image_uri))
    error_message = "Pin the immutable image digest."
  }
}
variable "artifact_bucket_name" { type = string }
variable "dashboard_desired_count" {
  type    = number
  default = 0
  validation {
    condition     = contains([0, 1], var.dashboard_desired_count)
    error_message = "Use zero or one private dashboard tasks."
  }
}
module "runtime" {
  source                  = "./modules/runtime"
  name                    = var.name
  region                  = var.region
  vpc_id                  = var.vpc_id
  private_subnet_ids      = var.private_subnet_ids
  image_uri               = var.image_uri
  artifact_bucket_name    = var.artifact_bucket_name
  dashboard_desired_count = var.dashboard_desired_count
}
output "state_machine_arn" { value = module.runtime.state_machine_arn }
output "cluster_arn" { value = module.runtime.cluster_arn }
