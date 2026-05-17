variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "location" {
  description = "GCP region/zone"
  type        = string
  default     = "us-central1"
}

variable "mlflow_version" {
  description = "MLflow version to deploy"
  type        = string
  default     = "2.12.1"
}

variable "database_password" {
  description = "PostgreSQL password for MLflow tracking server"
  type        = string
  sensitive   = true
}

variable "artifacts_bucket" {
  description = "GCS bucket for MLflow artifacts"
  type        = string
}

variable "instance_type" {
  description = "Cloud SQL instance type"
  type        = string
  default     = "db-n1-standard-2"
}

variable "labels" {
  description = "Labels to apply to resources"
  type        = map(string)
  default     = {}
}

variable "vpc_name" {
  description = "VPC network name"
  type        = string
  default     = "default"
}

variable "subnet_name" {
  description = "Subnet name"
  type        = string
  default     = "default"
}

variable "enable_gpu" {
  description = "Enable GPU support for training"
  type        = bool
  default     = false
}

variable "storage_size_gb" {
  description = "Database storage size in GB"
  type        = number
  default     = 50
}

variable "backup_enabled" {
  description = "Enable automated backups"
  type        = bool
  default     = true
}

variable "delete_protection" {
  description = "Prevent deletion of resources"
  type        = bool
  default     = true
}