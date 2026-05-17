locals {
  module_name    = "emr-cluster"
  default_tags    = merge(var.tags, { module = local.module_name })
  core_instances  = var.use_spot_instances ? 0 : var.core_instance_count
  task_instances  = var.use_spot_instances ? var.task_instance_count : 0
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_emr_cluster" "spark_cluster" {
  name          = "${var.cluster_name}-${var.environment}"
  release_label = var.release_label
  service_role  = var.emr_service_role_arn != "" ? var.emr_service_role_arn : aws_iam_role.emr_service_role[0].arn

  ec2_attributes {
    subnet_id                        = var.subnet_id
    emr_managed_master_security_group = length(var.security_groups) > 0 ? var.security_groups[0] : null
    emr_managed_slave_security_group  = length(var.security_groups) > 1 ? var.security_groups[1] : null
    instance_profile                = var.ec2_instance_profile_arn != "" ? var.ec2_instance_profile_arn : aws_iam_instance_profile.emr_ec2_profile[0].arn
    key_name                        = var.tags["ssh_key_name"] != null ? var.tags["ssh_key_name"] : null
  }

  master_instance_group {
    instance_type = var.master_instance_type
    instance_count = 1
    market        = "ON_DEMAND"
  }

  core_instance_group {
    instance_type  = var.core_instance_type
    instance_count = var.core_instance_count
    market         = var.use_spot_instances ? "SPOT" : "ON_DEMAND"
    bid_price      = var.use_spot_instances ? "${var.spot_bid_percentage}%" : null
    ebs_volume_config {
      ebs_volume_type       = "gp3"
      ebs_volume_size       = 100
      ebs_volumes_per_instance = 1
    }
  }

  dynamic "task_instance_group" {
    for_each = var.use_spot_instances && var.task_instance_count > 0 ? [1] : []
    content {
      instance_type  = var.task_instance_type
      instance_count = var.task_instance_count
      market         = "SPOT"
      bid_price      = "${var.spot_bid_percentage}%"
      ebs_volume_config {
        ebs_volume_type       = "gp3"
        ebs_volume_size       = 100
        ebs_volumes_per_instance = 1
      }
    }
  }

  dynamic "bootstrap_action" {
    for_each = var.bootstrap_actions
    content {
      name = bootstrap_action.value.name
      path = bootstrap_action.value.path
      args = bootstrap_action.value.args
    }
  }

  configurations_json = var.configurations_json != "" ? var.configurations_json : <<-JSON
    [
      {
        "Classification": "spark-defaults",
        "Properties": {
          "spark.dynamicAllocation.enabled": "true",
          "spark.dynamicAllocation.minExecutors": "1",
          "spark.dynamicAllocation.maxExecutors": "20",
          "spark.executor.memory": "8G",
          "spark.executor.cores": "4",
          "spark.sql.adaptive.enabled": "true",
          "spark.sql.adaptive.coalescePartitions.enabled": "true"
        }
      },
      {
        "Classification": "hadoop-kms-env",
        "Properties": {}
      }
    ]
    JSON

  applications = var.applications

  autoscaling_role = aws_iam_role.emr_autoscaling_role[0].arn

  dynamic "scale-out-behavior" {
    for_each = var.enable_autoscaling ? [1] : []
    content {
      scale_out_behavior = var.scale_down_behavior
    }
  }

  termination_protection = false

  tags = local.default_tags

  lifecycle {
    ignore_changes = [master_instance_group, core_instance_group]
  }
}

resource "aws_iam_role" "emr_service_role" {
  count = var.emr_service_role_arn == "" ? 1 : 0
  name  = "${local.module_name}-service-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = ["elasticmapreduce.amazonaws.com", "ec2.amazonaws.com"]
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = local.default_tags
}

resource "aws_iam_role_policy" "emr_service_policy" {
  count = var.emr_service_role_arn == "" ? 1 : 0
  name  = "${local.module_name}-service-policy-${var.environment}"
  role  = aws_iam_role.emr_service_role[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:*",
          "ec2:*",
          "iam:*",
          "logs:*",
          "cloudwatch:*",
          "glue:*"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "emr_ec2_profile_role" {
  count = var.ec2_instance_profile_arn == "" ? 1 : 0
  name  = "${local.module_name}-ec2-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = local.default_tags
}

resource "aws_iam_instance_profile" "emr_ec2_profile" {
  count = var.ec2_instance_profile_arn == "" ? 1 : 0
  name  = "${local.module_name}-ec2-profile-${var.environment}"
  role  = aws_iam_role.emr_ec2_profile_role[0].name
}

resource "aws_iam_role_policy" "emr_ec2_policy" {
  count = var.ec2_instance_profile_arn == "" ? 1 : 0
  name  = "${local.module_name}-ec2-policy-${var.environment}"
  role  = aws_iam_role.emr_ec2_profile_role[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:*",
          "glue:*",
          "cloudwatch:*",
          "logs:*"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "emr_autoscaling_role" {
  name = "${local.module_name}-autoscaling-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "elasticmapreduce.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = local.default_tags
}

resource "aws_iam_role_policy" "emr_autoscaling_policy" {
  name = "${local.module_name}-autoscaling-policy-${var.environment}"
  role = aws_iam_role.emr_autoscaling_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "elasticmapreduce:ModifyInstanceGroups",
        "elasticmappute:ListInstances",
        "cloudwatch:DescribeAlarms",
        "cloudwatch:PutMetricAlarm"
      ]
      Resource = "*"
    }]
  })
}

resource "aws_cloudwatch_log_group" "emr_logs" {
  name              = "/aws/emr/${var.cluster_name}-${var.environment}"
  retention_in_days = 30

  tags = local.default_tags
}

resource "aws_emr_security_configuration" "emr_security_config" {
  name = "${var.cluster_name}-security-${var.environment}"

  configuration = jsonencode({
    EncryptionConfiguration = {
      EnableInTransitEncryption = true
      EnableAtRestEncryption   = true
      EnableEbsEncryption      = true
    }
    KerberosConfiguration = {
      EnableKerberos = var.enable_ranger_kerberos
    }
    S3EncryptionConfiguration = {
      EnableEncryption = true
      EncryptionMode   = "SSE-S3"
    }
  })
}

resource "aws_emr_instance_group" "task_autoscaling" {
  count = var.enable_autoscaling && var.use_spot_instances ? 1 : 0

  cluster_id     = aws_emr_cluster.spark_cluster.id
  instance_group = "TASK"
  instance_type  = var.task_instance_type
  instance_count = 0

  autoscaling_policy = jsonencode({
    rules = [
      {
        name      = "ScaleOutOnYarnMemory"
        action    = { market = "SPOT", instance选购 = "ADD" }
        trigger   = { cloud_watch_alarm_definition = { comparison = "GT", threshold = 80, period = 300, metric = "YARNMemoryAvailablePercentage" } }
      },
      {
        name      = "ScaleInOnYarnMemory"
        action    = { market = "SPOT", instance选购 = "REMOVE" }
        trigger   = { cloud_watch_alarm_definition = { comparison = "LT", threshold = 30, period = 600, metric = "YARNMemoryAvailablePercentage" } }
      }
    ]
  })
}

output "cluster_id" {
  description = "EMR cluster ID"
  value       = aws_emr_cluster.spark_cluster.id
}

output "cluster_name" {
  description = "EMR cluster name"
  value       = aws_emr_cluster.spark_cluster.name
}

output "master_public_dns" {
  description = "Master node public DNS"
  value       = aws_emr_cluster.spark_cluster.master_public_dns
}

output "manager_address" {
  description = "EMR manager address"
  value       = aws_emr_cluster.spark_cluster.master_public_dns
}