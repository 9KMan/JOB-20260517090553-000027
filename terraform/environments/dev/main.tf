terraform {
  required_version = ">= 1.5.0"

  backend "local" {
    path = "terraform.tfstate"
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
      Environment = "development"
      ManagedBy   = "terraform"
      Project     = "mlops-platform"
    }
  }
}

provider "google" {
  project = "mlops-platform-dev"
  region  = "us-central1"
}

variable "model_name" {
  description = "Model name for deployment"
  type        = string
  default     = "fraud-detection-v1-dev"
}

module "mlflow" {
  source = "../../modules/mlflow"

  project_id        = "mlops-platform-dev"
  location          = "us-central1"
  mlflow_version    = "2.12.1"
  database_password = "dev-password-change-me"
  artifacts_bucket  = ""
  instance_type     = "db-g1-small"
  storage_size_gb   = 20
  enable_gpu        = false
  delete_protection = false

  labels = {
    environment = "dev"
    domain      = "dev.ml.example.com"
    cost_center = "mlops-dev"
  }

  vpc_name    = "default"
  subnet_name = "default"
}

module "sagemaker" {
  source = "../../modules/sagemaker"

  environment            = "dev"
  model_name             = var.model_name
  model_image_uri        = "123456789012.dkr.ecr.us-east-1.amazonaws.com/fraud-detection:dev"
  model_data_url         = "s3://mlops-artifacts-dev/models/fraud-detection-dev.tar.gz"
  instance_type          = "ml.m5.large"
  initial_instance_count = 1
  enable_model_deployment = true
  enable_monitoring      = false
  monitoring_cron        = "cron(0 * ? * * *)"

  environment_variables = {
    MODEL_NAME = var.model_name
    LOG_LEVEL  = "DEBUG"
  }

  tags = {
    Environment = "development"
    ManagedBy   = "terraform"
  }
}

module "emr" {
  source = "../../modules/emr"

  environment       = "dev"
  cluster_name      = "mlops-spark-dev"
  release_label     = "emr-7.1.0"
  master_instance_type = "m5.xlarge"
  core_instance_type   = "m5.xlarge"
  core_instance_count  = 1
  task_instance_type   = "m5.xlarge"
  task_instance_count  = 0
  use_spot_instances   = false

  subnet_id   = "subnet-0123456789abcdef0"
  enable_autoscaling = false

  applications = ["Spark", "Livy"]

  tags = {
    Environment = "development"
    ManagedBy   = "terraform"
  }
}

module "eks" {
  source = "../../modules/eks"

  environment      = "dev"
  cluster_name     = "mlops-platform-dev"
  kubernetes_version = "1.29"

  vpc_id            = "vpc-0123456789abcdef0"
  private_subnet_ids = ["subnet-0123456789abcdef0"]
  public_subnet_ids  = ["subnet-0123456789abcdef1"]

  worker_instance_types = ["m5.xlarge"]
  worker_disk_size     = 50
  min_worker_count     = 1
  max_worker_count     = 5
  desired_worker_count = 2
  enable_gpu_workers   = false

  enable_irsa            = true
  enable_prometheus      = true
  enable_alb_ingress     = true
  enable_cluster_autoscaler = false

  tags = {
    Environment = "development"
    ManagedBy   = "terraform"
  }
}