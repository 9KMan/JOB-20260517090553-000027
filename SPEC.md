# Senior AI & Data Platform Engineer — MLOps / Data Pipelines / Cloud

## 1. Project Overview

**Client:** Engineering Consultancy (FinTech, Healthcare, Retail, SaaS)
**Goal:** Design and operate cloud-native ML + data platforms — MLOps pipelines, ETL/ELT, observability, client-facing platform decisions.
**Duration:** 1–3 months, <30 hrs/week, part-time consulting
**Tech Stack:** AWS/GCP, Airflow, Spark, Kafka, dbt, MLflow/Kubeflow, Kubernetes, Terraform

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLIENT DOMAINS                                  │
│  FinTech    Healthcare      Retail         SaaS                        │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   CONSULTING LAYER       │
                    │  (This Engagement)       │
                    │  Architecture decisions  │
                    │  Migration guidance      │
                    │  Cost optimization       │
                    └─────────────┬─────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
┌───────▼────────┐    ┌──────────▼────────┐    ┌──────────▼────────┐
│  ML Platform    │    │   Data Platform   │    │  Observability     │
│  (MLflow/TFX/   │    │   (Airflow/Spark/│    │  (Prometheus/     │
│   SageMaker)    │    │    Kafka/dbt)    │    │   Grafana/OTel)   │
└───────┬─────────┘    └──────────┬────────┘    └──────────┬────────┘
        │                         │                         │
        └─────────────────────────┴─────────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   CLOUD INFRASTRUCTURE   │
                    │  AWS (SageMaker/EMR/EKS) │
                    │  or GCP (Vertex/GKE)    │
                    │  Terraform + Helm       │
                    └─────────────────────────┘
```

---

## 3. Core Workstreams

### Workstream 1: MLOps Platform
- **Model versioning:** MLflow Model Registry — stage promotion (staging→production), model lineage, version comparisons
- **Drift detection:** Evidently AI or custom Python monitors on feature + prediction distributions; alerts when PSI/KS exceeds thresholds
- **Auto-scaling:** SageMaker endpoint auto-scaling or Kubernetes Horizontal Pod Autoscaler with custom metrics (prediction latency, queue depth)
- **Continuous training:** Kubeflow Pipeline or SageMaker Pipelines — trigger retraining on schedule or drift signal; A/B shadow deployment before full rollout

### Workstream 2: ETL/ELT Data Pipelines
- **Batch pipelines:** Apache Airflow DAGs → Spark on EMR/EMR Serverless or Databricks → dbt transformations on Delta Lake/Iceberg
- **Real-time pipelines:** Kafka Connect → Flink → Delta Lake; schema registry with Confluent; exactly-once semantics
- **Data quality:** Great Expectations or dbt tests at transformation layer; null/freshness/scheme checks; dead-letter queues on failures

### Workstream 3: Observability Platform
- **Metrics:** Prometheus + Grafana (or CloudWatch + GMD for AWS/GCP); golden signals: latency, traffic, errors, saturation
- **Traces:** OpenTelemetry instrumentation on Python services → Tempo (Grafana) or Jaeger
- **Logs:** structured JSON → Loki or CloudWatch Logs Insights
- **Dashboards:** per-service SLO dashboard + MLOps-specific (model latency p95, drift score, pipeline success rate)

### Workstream 4: Cloud Platform Decisions & Migration
- **Cost optimization:** reserved instance/Spot mix for Spark EMR; auto-pause dev environments; BigQuery reservation sizing
- **Migration:** lift-and-shift评估, data validation during migration, rollback procedures
- **IaC:** Terraform modules for platform components; Helm charts for Kubernetes workloads; Atlantis for PR-based apply

---

## 4. Data Model

```
MLOps Platform Tables:
  models (id, name, version, stage, created_at, metrics_json)
  model_versions (id, model_id, training_run_id, artifact_uri, framework)
  drift_alerts (id, model_id, feature_name, drift_score, triggered_at)
  pipeline_runs (id, dag_id, state, started_at, completed_at, error_msg)

Data Platform Tables:
  pipeline_metadata (pipeline_id, source, target, last_run_at, watermark)
  data_quality_results (run_id, table, check, passed, severity, logged_at)
```

---

## 5. API Design

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ml/models` | GET | List registered models with versions |
| `POST /ml/models/{id}/stage` | POST | Promote model stage (staging→production) |
| `GET /ml/drift/{model_id}` | GET | Current drift scores per feature |
| `GET /pipelines` | GET | List Airflow DAGs with last run status |
| `POST /pipelines/{id}/trigger` | POST | Manual pipeline trigger |
| `GET /pipelines/{id}/runs/{run_id}` | GET | Get run details + logs URL |
| `GET /observability/slos` | GET | SLO dashboard summary |
| `GET /observability/alerts` | GET | Active alerts with severity |

---

## 6. Technical Decisions

1. **MLflow vs. Kubeflow:** MLflow for teams that want simplicity — Model Registry + Experiments UI is mature. Kubeflow when you need multi-user pipeline orchestration with complex DAGs. Recommend MLflow as default unless client already has Kubernetes maturity.
2. **Spark on EMR vs. Databricks:** EMR for cost-sensitive batch workloads (Spot instances, auto-termination). Databricks for teams that want managed notebooks + Unity Catalog integration.
3. **Kafka vs. Kinesis:** Kafka for durability + schema registry (Confluent) and cross-cloud portability. Kinesis for AWS-only shops that want native CloudWatch integration.
4. **dbt vs. Spark SQL transformations:** dbt for SQL-first teams and business logic transformations. Spark for heavy ETL or data wrangling that exceeds SQL expressibility.
5. **Terraform modules:** enforce tagging standards, cost allocation labels, and security baselines (encryption at rest, no public S3 buckets) via module-level enforcement.

---

## 7. Out of Scope

- Frontend/dashboard development (React or similar)
- Custom model development (model training itself — infrastructure only)
- Hardware procurement or cloud contract negotiation
- Mobile application work

---

## 8. Success Metrics

- MLOps platform: 0 failed model deployments (verified by pipeline run history), drift detection alerts within 15 minutes of threshold breach
- Data pipelines: >99% on-time completion rate, <0.1% data quality failures
- Observability: SLO dashboard refreshes every 60s, all services have trace instrumentation
- Client deliverables: documented architecture decision records (ADRs) for each platform decision, runbook for on-call engineers