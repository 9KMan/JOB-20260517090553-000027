# MLOps Platform - Production Infrastructure

Cloud-native ML + data platform for engineering consultancy. Supports MLOps pipelines, ETL/ELT workloads, and observability for FinTech, Healthcare, Retail, and SaaS clients.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLIENT DOMAINS                                  │
│  FinTech    Healthcare      Retail         SaaS                        │
└─────────────────────────────────┬───────────────────────────────────────┘
                                   │
                     ┌─────────────▼─────────────┐
                     │   CONSULTING LAYER       │
                     │  Architecture decisions  │
                     │  Migration guidance      │
                     │  Cost optimization       │
                     └─────────────┬─────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
┌───────▼────────┐    ┌──────────▼────────┐    ┌──────────▼────────┐
│  ML Platform    │    │   Data Platform   │    │  Observability     │
│  (MLflow/SageMaker)   │    │   (Airflow/Spark/│    │  (Prometheus/     │
│                   │    │    Kafka/dbt)    │    │   Grafana/OTel)   │
└───────┬─────────┘    └──────────┬────────┘    └──────────┬────────┘
        │                         │                         │
        └─────────────────────────┴─────────────────────────┘
                                   │
                     ┌─────────────▼─────────────┐
                     │   CLOUD INFRASTRUCTURE   │
                     │  AWS (SageMaker/EMR/EKS) │
                     │  GCP (Vertex/GKE)       │
                     │  Terraform + Helm       │
                     └─────────────────────────┘
```

## Contents

### Infrastructure as Code (Terraform)

- `terraform/modules/mlflow/` - MLflow tracking server on GCP
- `terraform/modules/sagemaker/` - SageMaker endpoints on AWS
- `terraform/modules/emr/` - EMR Spark clusters
- `terraform/modules/eks/` - EKS Kubernetes clusters
- `terraform/environments/prod/` - Production configuration
- `terraform/environments/dev/` - Development configuration

### Airflow DAGs

- `airflow/dags/etl_spark_batch.py` - Batch ETL with Spark on EMR
- `airflow/dags/etl_kafka_flink.py` - Real-time streaming with Kafka/Flink
- `airflow/dags/ml_model_training.py` - ML model training pipeline
- `airflow/dags/dbt_transformation.py` - dbt transformation pipeline

### Monitoring

- `monitoring/prometheus/prometheus.yml` - Prometheus scrape configuration
- `monitoring/prometheus/alerts.yml` - Alert rules
- `monitoring/grafana/dashboards/mlops-platform.json` - Grafana dashboard

### MLOps

- `mlops/drift_detection/monitor.py` - Feature drift detection (PSI/KS metrics)

### Documentation

- `docs/adrs/` - Architecture Decision Records
- `runbooks/` - On-call runbooks and deployment guides

## Quick Start

### Deploy MLflow

```bash
cd terraform/modules/mlflow
terraform init
terraform apply -var-file=prod.tfvars
```

### Deploy EKS Cluster

```bash
cd terraform/modules/eks
terraform init
terraform apply -var-file=prod.tfvars

# Configure kubectl
aws eks update-kubeconfig --region us-east-1 --name mlops-platform-prod
```

### Deploy Monitoring

```bash
kubectl apply -f monitoring/prometheus/prometheus.yml
kubectl apply -f monitoring/prometheus/alerts.yml
```

## Key Decisions

See `docs/adrs/` for detailed architecture decisions:

- **ADR-001**: MLflow Model Registry over Kubeflow
- **ADR-002**: EMR for batch Spark over Databricks
- **ADR-003**: Kafka over Kinesis for multi-cloud streaming

## Tech Stack

| Component | Technology |
|-----------|------------|
| MLOps | MLflow, SageMaker, Kubeflow |
| Batch ETL | Airflow, Spark on EMR, dbt, Delta Lake |
| Real-time | Kafka, Flink, Schema Registry |
| Observability | Prometheus, Grafana, OpenTelemetry |
| IaC | Terraform, Helm, Kubernetes (EKS/GKE) |
| Cloud | AWS (primary), GCP (secondary) |

## Success Metrics

- **MLOps platform**: 0 failed model deployments, drift alerts within 15 min
- **Data pipelines**: >99% on-time completion, <0.1% data quality failures
- **Observability**: SLO dashboard refreshes every 60s
- **Deliverables**: ADRs and runbooks for all platform decisions