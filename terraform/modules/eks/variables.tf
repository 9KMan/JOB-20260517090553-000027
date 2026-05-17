variable "environment" {
  description = "Environment name"
  type        = string
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version"
  type        = string
  default     = "1.29"
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "Public subnet IDs"
  type        = list(string)
}

variable "enable_irsa" {
  description = "Enable IAM Roles for Service Accounts"
  type        = bool
  default     = true
}

variable "enable_managed_node_groups" {
  description = "Enable managed node groups"
  type        = bool
  default     = true
}

variable "worker_instance_types" {
  description = "Worker instance types"
  type        = list(string)
  default     = ["m5.xlarge"]
}

variable "worker_disk_size" {
  description = "Worker disk size in GB"
  type        = number
  default     = 100
}

variable "min_worker_count" {
  description = "Minimum worker count"
  type        = number
  default     = 2
}

variable "max_worker_count" {
  description = "Maximum worker count"
  type        = number
  default     = 10
}

variable "desired_worker_count" {
  description = "Desired worker count"
  type        = number
  default     = 3
}

variable "enable_gpu_workers" {
  description = "Enable GPU worker nodes"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

variable "enable_prometheus" {
  description = "Enable Prometheus monitoring"
  type        = bool
  default     = true
}

variable "enable_alb_ingress" {
  description = "Enable ALB ingress controller"
  type        = bool
  default     = true
}

variable "enable_cluster_autoscaler" {
  description = "Enable cluster autoscaler"
  type        = bool
  default     = true
}