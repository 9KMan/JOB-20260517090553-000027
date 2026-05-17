data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  module_name = "sagemaker-endpoint"
  environment = var.environment
  account_id  = data.aws_caller_identity.current.account_id
  region      = data.aws_caller_identity.current.region
}

resource "aws_iam_role" "sagemaker_execution_role" {
  name = "${local.module_name}-execution-${local.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "sagemaker.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "sagemaker_execution_policy" {
  name = "${local.module_name}-execution-policy-${local.environment}"
  role = aws_iam_role.sagemaker_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:DescribeLogStreams",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "arn:aws:s3:::${var.model_artifacts_bucket}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:DescribeRepositories",
          "ecr:DescribeImages",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "autoscaling_policy" {
  name = "${local.module_name}-autoscaling-${local.environment}"
  role = aws_iam_role.sagemaker_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "cloudwatch:DescribeAlarms",
        "cloudwatch:PutMetricAlarm",
        "cloudwatch:DeleteAlarms"
      ]
      Resource = "*"
    }]
  })
}

resource "aws_s3_bucket" "model_artifacts" {
  count  = var.model_artifacts_bucket == "" ? 1 : 0
  bucket = "${local.module_name}-artifacts-${local.environment}-${local.account_id}"

  tags = var.tags

  versioning {
    enabled = true
  }

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
}

resource "aws_s3_bucket_public_access_block" "model_artifacts_block" {
  count  = var.model_artifacts_bucket == "" ? 1 : 0
  bucket = aws_s3_bucket.model_artifacts[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_sagemaker_model" "ml_model" {
  count        = var.enable_model_deployment ? 1 : 0
  name         = "${var.model_name}-${local.environment}"
  execution_role_arn = aws_iam_role.sagemaker_execution_role.arn

  primary_container {
    image_url  = var.model_image_uri
    model_data_url = var.model_data_url
    environment = var.environment_variables
  }

  tags = var.tags
}

resource "aws_sagemaker_endpoint_configuration" "endpoint_config" {
  count = var.enable_model_deployment ? 1 : 0
  name  = "${var.model_name}-config-${local.environment}"

  production_variants {
    variant_name           = "${var.model_name}-variant"
    model_name             = aws_sagemaker_model.ml_model[0].name
    initial_instance_count = var.initial_instance_count
    instance_type          = var.instance_type
    initial_variant_weight = 1.0

    auto_monitoring_config {
      monitoring_schedule_config {
        monitoring_job_definition_name = aws_sagemaker_model_monitor.job_monitoring[0].name if var.enable_monitoring else null
      }
    }
  }

  tags = var.tags
}

resource "aws_sagemaker_endpoint" "ml_endpoint" {
  count = var.enable_model_deployment ? 1 : 0
  name  = "${var.model_name}-endpoint-${local.environment}"

  endpoint_config_name = aws_sagemaker_endpoint_configuration.endpoint_config[0].name

  tags = var.tags

  lifecycle_policy {
    update_replace_policy = "Delete"
  }
}

resource "aws_sagemaker_model_monitor" "job_monitoring" {
  count = var.enable_monitoring ? 1 : 0
  name  = "${var.model_name}-monitor-${local.environment}"

  execution_role_arn = aws_iam_role.sagemaker_execution_role.arn

  baseline_config {
    s3_uri = "s3://${var.model_artifacts_bucket != "" ? var.model_artifacts_bucket : aws_s3_bucket.model_artifacts[0].id}/baselining/"
  }

  monitoring_schedule_config {
    monitoring_job_type             = "ModelQuality"
    schedule_cron_expression         = var.monitoring_cron
    monitoring_execution_baseline_uri = "s3://${var.model_artifacts_bucket}/baseline.json"
    output_config {
      s3_uri = "s3://${var.model_artifacts_bucket != "" ? var.model_artifacts_bucket : aws_s3_bucket.model_artifacts[0].id}/monitoring-output/"
    }
  }
}

resource "aws_cloudwatch_dashboard" "sagemaker_dashboard" {
  count = var.enable_model_deployment ? 1 : 0
  dashboard_name = "${var.model_name}-dashboard-${local.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          title = "Invocation Count"
          metrics = [[{ expression = "SELECT SUM(Invocations) FROM SCHEMA(\"AWS/SageMaker\", EndpointName)", label = "Invocations" }]]
          period = 300
          stat = "Sum"
        }
      },
      {
        type = "metric"
        properties = {
          title = "Invocation Latency p99"
          metrics = [[{ expression = "SELECT AVG(Involvement) FROM SCHEMA(\"AWS/SageMaker\", EndpointName)", label = "Latency" }]]
          period = 300
          stat = "Average"
        }
      },
      {
        type = "metric"
        properties = {
          title = "Model Latency p99"
          metrics = [["AWS/SageMaker", "ModelLatency", "EndpointName", var.model_name]]
          period = 300
          stat = "p99"
        }
      },
      {
        type = "metric"
        properties = {
          title = "CPU Utilization"
          metrics = [["CWAgent", "CPUUtilization", "InstanceId", "sagemaker"]]
          period = 60
          stat = "Average"
        }
      }
    ]
  })
}

output "endpoint_name" {
  description = "SageMaker endpoint name"
  value       = var.enable_model_deployment ? aws_sagemaker_endpoint.ml_endpoint[0].name : ""
}

output "model_artifacts_bucket" {
  description = "S3 bucket for model artifacts"
  value       = var.model_artifacts_bucket != "" ? var.model_artifacts_bucket : aws_s3_bucket.model_artifacts[0].id
}

output "execution_role_arn" {
  description = "SageMaker execution role ARN"
  value       = aws_iam_role.sagemaker_execution_role.arn
}