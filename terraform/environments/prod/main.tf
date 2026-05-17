terraform {
  required_version = ">= 1.5.0"

  backend "s3" {
    bucket = "terraform-state-prod-12345"
    key    = "mlops-platform/prod/terraform.tfstate"
    region = "us-east-1"
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      Environment = "production"
      ManagedBy   = "terraform"
      Project     = "mlops-platform"
    }
  }
}

provider "google" {
  project = "mlops-platform-prod"
  region  = "us-central1"
}

variable "model_name" {
  description = "Model name for deployment"
  type        = string
  default     = "fraud-detection-v1"
}

module "mlflow" {
  source = "../../modules/mlflow"

  project_id        = "mlops-platform-prod"
  location          = "us-central1"
  mlflow_version    = "2.12.1"
  database_password = var.mlflow_db_password
  artifacts_bucket  = "mlops-artifacts-prod"
  instance_type     = "db-n1-standard-4"
  storage_size_gb   = 100
  enable_gpu        = false
  delete_protection = true

  labels = {
    environment = "prod"
    domain      = "ml.example.com"
    cost_center = "mlops"
  }

  vpc_name     = "projects/mlops-platform-prod/global/networks/default"
  subnet_name  = "regions/us-central1/subnetworks/mlflow-private"
}

module "sagemaker" {
  source = "../../modules/sagemaker"

  environment            = "prod"
  model_name             = var.model_name
  model_image_uri        = "123456789012.dkr.ecr.us-east-1.amazonaws.com/fraud-detection:latest"
  model_data_url         = "s3://mlops-artifacts-prod/models/fraud-detection-v1.tar.gz"
  instance_type          = "ml.m5.4xlarge"
  initial_instance_count = 2
  enable_model_deployment = true
  enable_monitoring      = true
  monitoring_cron        = "cron(0 * ? * * *)"

  environment_variables = {
    MODEL_NAME = var.model_name
    LOG_LEVEL  = "INFO"
  }

  tags = {
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

module "emr" {
  source = "../../modules/emr"

  environment       = "prod"
  cluster_name      = "mlops-spark"
  release_label     = "emr-7.1.0"
  master_instance_type = "m5.4xlarge"
  core_instance_type   = "m5.2xlarge"
  core_instance_count  = 4
  task_instance_type   = "m5.xlarge"
  task_instance_count  = 8
  use_spot_instances   = true
  spot_bid_percentage = 60

  subnet_id   = "subnet-0123456789abcdef0"
  security_groups = ["sg-0123456789abcdef0", "sg-abcdef0123456789"]
  enable_autoscaling = true
  min_core_instances = 2
  max_core_instances = 20

  applications = ["Spark", "Livy", "JupyterEnterpriseGateway", "Hive", "Presto"]

  tags = {
    Environment = "production"
    ManagedBy   = "terraform"
    CostCenter  = "mlops"
  }
}

module "eks" {
  source = "../../modules/eks"

  environment      = "prod"
  cluster_name     = "mlops-platform"
  kubernetes_version = "1.29"

  vpc_id            = "vpc-0123456789abcdef0"
  private_subnet_ids = ["subnet-0123456789abcdef0", "subnet-abcdef0123456789"]
  public_subnet_ids  = ["subnet-0123456789abcdef1", "subnet-abcdef0123456788"]

  worker_instance_types = ["m5.xlarge", "m5.2xlarge"]
  worker_disk_size     = 100
  min_worker_count     = 3
  max_worker_count     = 20
  desired_worker_count = 5
  enable_gpu_workers   = true

  enable_irsa            = true
  enable_prometheus      = true
  enable_alb_ingress     = true
  enable_cluster_autoscaler = true

  tags = {
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

variable "mlflow_db_password" {
  description = "MLflow database password"
  type        = string
  sensitive   = true
}

output "mlflow_endpoint" {
  description = "MLflow tracking server endpoint"
  value       = "http://${module.mlflow.mlflow_server_ip}:8000"
}

output "sagemaker_endpoint" {
  description = "SageMaker endpoint name"
  value       = module.sagemaker.endpoint_name
}

output "emr_cluster_id" {
  description = "EMR cluster ID"
  value       = module.emr.cluster_id
}

output "eks_cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}