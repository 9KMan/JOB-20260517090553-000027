variable "environment" {
  description = "Environment name"
  type        = string
}

variable "cluster_name" {
  description = "EMR cluster name"
  type        = string
}

variable "release_label" {
  description = "EMR release version"
  type        = string
  default     = "emr-7.1.0"
}

variable "master_instance_type" {
  description = "Master node instance type"
  type        = string
  default     = "m5.xlarge"
}

variable "core_instance_type" {
  description = "Core node instance type"
  type        = string
  default     = "m5.xlarge"
}

variable "core_instance_count" {
  description = "Number of core instances"
  type        = number
  default     = 2
}

variable "task_instance_type" {
  description = "Task node instance type"
  type        = string
  default     = "m5.xlarge"
}

variable "task_instance_count" {
  description = "Number of task instances"
  type        = number
  default     = 2
}

variable "use_spot_instances" {
  description = "Use spot instances for task nodes"
  type        = bool
  default     = true
}

variable "spot_bid_percentage" {
  description = "Bid percentage for spot instances"
  type        = number
  default     = 60
}

variable "subnet_id" {
  description = "VPC subnet ID"
  type        = string
}

variable "security_groups" {
  description = "Security groups for EMR cluster"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

variable "enable_autoscaling" {
  description = "Enable EMR autoscaling"
  type        = bool
  default     = true
}

variable "min_core_instances" {
  description = "Minimum core instances"
  type        = number
  default     = 2
}

variable "max_core_instances" {
  description = "Maximum core instances"
  type        = number
  default     = 10
}

variable "scale_down_behavior" {
  description = "Scale down behavior"
  type        = string
  default     = "TERMINATE_AT_TASK_COMPLETION"
}

variable "emr_service_role_arn" {
  description = "EMR service role ARN"
  type        = string
  default     = ""
}

variable "ec2_instance_profile_arn" {
  description = "EC2 instance profile ARN"
  type        = string
  default     = ""
}

variable "enable_glue_catalog" {
  description = "Enable AWS Glue as metastore"
  type        = bool
  default     = false
}

variable "enable_ranger_kerberos" {
  description = "Enable Ranger Kerberos integration"
  type        = bool
  default     = false
}

variable "applications" {
  description = "EMR applications to install"
  type        = list(string)
  default     = ["Spark", "Livy", "JupyterEnterpriseGateway"]
}

variable "configurations_json" {
  description = "EMR configurations JSON"
  type        = string
  default     = ""
}

variable "bootstrap_actions" {
  description = "Bootstrap actions"
  type = list(object({
    name = string
    path = string
    args = list(string)
  }))
  default = []
}