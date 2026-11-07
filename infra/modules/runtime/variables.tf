variable "name" { type = string }
variable "region" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "image_uri" { type = string }
variable "artifact_bucket_name" { type = string }
variable "dashboard_desired_count" { type = number }
