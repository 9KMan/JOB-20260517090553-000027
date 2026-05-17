# MLOps Platform: Deployment Guide

## Overview

This document covers the complete deployment process for the MLOps platform components including MLflow, SageMaker, EMR, and EKS clusters.

## Prerequisites

- AWS CLI configured with appropriate credentials
- Terraform >= 1.5.0
- kubectl >= 1.29
- helm >= 3.12
- Python >= 3.10 with boto3

## Environment Setup

### 1. Configure AWS Credentials

```bash
# Set up AWS profile
aws configure --profile mlops-production
export AWS_PROFILE=mlops-production

# Verify credentials
aws sts get-caller-identity
```

### 2. Install Required Tools

```bash
# Terraform
terraform_version="1.5.0"
wget https://releases.hashicorp.com/terraform/${terraform_version}/terraform_${terraform_version}_linux_amd64.zip
unzip terraform_${terraform_version}_linux_amd64.zip -d /usr/local/bin/

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
mv kubectl /usr/local/bin/

# Helm
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

## Deployment Order

Deploy components in this order to ensure dependencies are met:

1. **VPC & Networking** (if not pre-existing)
2. **Terraform Backend** (S3 bucket for state)
3. **MLflow** (tracking server - deploy first)
4. **SageMaker** (model deployment)
5. **EMR** (Spark processing)
6. **EKS** (Kubernetes workloads)
7. **Monitoring Stack** (Prometheus, Grafana)

---

## 1. VPC & Networking

```bash
cd terraform/environments/prod

# Review and update variables
vim variables.tf

# Initialize Terraform
terraform init

# Plan deployment
terraform plan -out=tfplan

# Apply
terraform apply tfplan
```

## 2. MLflow Deployment

### Deploy MLflow Server

```bash
cd terraform/modules/mlflow

# Create tfvars file
cat > prod.tfvars << EOF
project_id        = "mlops-platform-prod"
location          = "us-central1"
mlflow_version    = "2.12.1"
database_password = "your-secure-password"
artifacts_bucket  = "mlops-artifacts-prod"
instance_type     = "db-n1-standard-4"
storage_size_gb   = 100

labels = {
  environment = "prod"
  domain      = "ml.example.com"
  cost_center = "mlops"
}
EOF

terraform plan -var-file=prod.tfvars
terraform apply -var-file=prod.tfvars
```

### Verify MLflow Deployment

```bash
# Get MLflow server IP
terraform output mlflow_server_ip

# Test connectivity
curl http://<MLFLOW_IP>:8000/health

# Access MLflow UI
open http://<MLFLOW_IP>:8000
```

## 3. SageMaker Deployment

### Configure Model Deployment

```bash
cd terraform/modules/sagemaker

cat > prod.tfvars << EOF
environment      = "prod"
model_name       = "fraud-detection-v1"
model_image_uri  = "123456789012.dkr.ecr.us-east-1.amazonaws.com/fraud-detection:latest"
model_data_url   = "s3://mlops-artifacts-prod/models/fraud-detection-v1.tar.gz"
instance_type    = "ml.m5.4xlarge"
initial_instance_count = 2
enable_model_deployment = true

environment_variables = {
  MODEL_NAME = "fraud-detection-v1"
  LOG_LEVEL  = "INFO"
}

tags = {
  Environment = "production"
  ManagedBy   = "terraform"
}
EOF

terraform apply -var-file=prod.tfvars
```

### Verify SageMaker Endpoint

```bash
# Get endpoint status
aws sagemaker describe-endpoint --endpoint-name fraud-detection-v1-prod

# Test endpoint
aws sagemaker invoke-endpoint \
  --endpoint-name fraud-detection-v1-prod \
  --body '{"instances": [{"features": [1.0, 2.0, 3.0]}]}' \
  --content-type application/json
```

## 4. EMR Deployment

### Deploy EMR Cluster

```bash
cd terraform/modules/emr

cat > prod.tfvars << EOF
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
enable_autoscaling = true

tags = {
  Environment = "production"
  ManagedBy   = "terraform"
  CostCenter  = "mlops"
}
EOF

terraform apply -var-file=prod.tfvars
```

### Connect to EMR

```bash
# Get master node DNS
terraform output master_public_dns

# SSH to master
ssh -i ~/keys/emr-key.pem hadoop@<MASTER_DNS>

# Check Spark UI
# Spark History Server typically on port 18080
open http://<MASTER_DNS>:18080

# Submit test job
spark-submit --class org.apache.spark.examples.SparkPi \
  --master yarn \
  --deploy-mode cluster \
  /usr/lib/spark/examples/jars/spark-examples.jar 100
```

## 5. EKS Deployment

### Deploy Kubernetes Cluster

```bash
cd terraform/modules/eks

cat > prod.tfvars << EOF
environment         = "prod"
cluster_name       = "mlops-platform"
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
EOF

terraform apply -var-file=prod.tfvars
```

### Configure kubectl

```bash
# Update kubeconfig
aws eks update-kubeconfig --region us-east-1 --name mlops-platform-prod

# Verify cluster access
kubectl get nodes
kubectl get pods -A
```

### Deploy Applications to EKS

```bash
# Add Helm repos
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Deploy monitoring stack
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --values monitoring/prometheus/values.yaml

helm install grafana grafana/grafana \
  --namespace monitoring \
  --values monitoring/grafana/values.yaml
```

## 6. Airflow Deployment

### Using Astro CLI (Recommended)

```bash
# Install Astro CLI
curl -sL https://install.astronomer.io | bash

# Initialize project
mkdir airflow && cd airflow
astro dev init

# Copy DAGs
cp -r ../airflow/dags/* dags/

# Deploy to Astronomer
astro deploy --deployment mlops-airflow
```

### Alternative: Helm on EKS

```bash
helm repo add apache-airflow https://airflow.apache.org
helm install airflow apache-airflow/airflow \
  --namespace airflow \
  --create-namespace \
  --values airflow/helm/values.yaml
```

## Verification Checklist

After deployment, verify all components:

```bash
# MLflow
curl http://<MLFLOW_IP>:8000/api/2.0/mlflow/experiments/list

# SageMaker
aws sagemaker list-endpoints --query 'Endpoints[?Status==`InService`]'

# EMR
aws emr list-clusters --query 'Clusters[?Status==`RUNNING`]'

# EKS
kubectl get nodes --show-labels
kubectl get svc -A

# Airflow
open http://airflow.example.com/admin/
```

## Rollback Procedures

### MLflow Rollback

```bash
# Restore previous version
gcloud compute instances stop mlflow-server-prod
gcloud compute snapshots create mlflow-backup-$(date +%Y%m%d)
# Deploy from snapshot if needed
```

### SageMaker Rollback

```bash
# Update endpoint to previous configuration
aws sagemaker update-endpoint \
  --endpoint-name fraud-detection-v1-prod \
  --endpoint-config-name fraud-detection-v1-prod-config-previous
```

### EMR Rollback

```bash
# Terminate current cluster, restore from last known good state
aws emr terminate-job-flows --job-flow-ids j-XXXXXXXX
# Previous cluster can be started from Terraform state
terraform apply -var-file=prod.tfvars
```

## Cleanup

```bash
# Destroy in reverse order of deployment
terraform destroy -var-file=prod.tfvars  # EKS first
terraform destroy -var-file=prod.tfvars  # Then EMR
terraform destroy -var-file=prod.tfvars  # Then SageMaker
terraform destroy -var-file=prod.tfvars  # Finally MLflow
```