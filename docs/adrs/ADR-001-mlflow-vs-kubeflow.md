# ADR-001: MLflow Model Registry over Kubeflow for Standard MLOps

## Status
Accepted

## Date
2024-01-15

## Context
The platform team needs to select an MLOps framework for managing model lifecycle (versioning, stage promotion, lineage tracking). The organization has:
- 3-5 models in production currently
- A team of 4 ML engineers
- No existing Kubernetes infrastructure
- Limited budget for operational overhead

## Decision
We will use **MLflow Model Registry** as the primary MLOps platform for standard model lifecycle management.

## Rationale

### MLflow Model Registry Selected Because:

1. **Simplicity of Operations**
   - Single-service deployment (no Kubernetes required for basic functionality)
   - PostgreSQL-backed persistence for model metadata
   - Gunicorn/Flask stack that's well-understood by the team
   - Average setup time: 2 hours vs. Kubeflow's 2-3 days

2. **Model Registry Maturity**
   - Stage promotion (Staging → Production) with approval workflows
   - Model lineage tracking across training runs
   - Version comparison for metrics across iterations
   - Built-in model serving for experimentation

3. **Cost Efficiency**
   - Can run on a single t3.medium instance for teams with <10 models
   - No Kubernetes cluster overhead (~$200-500/month for a small cluster)
   - Lower maintenance burden (1 engineer can own it part-time)

### Kubeflow Rejected Because:

1. **Operational Overhead**
   - Requires Kubernetes expertise for debugging
   - Multiple components (TFJob, PyTorchJob, Katib, Pipeline) need separate monitoring
   - Upgrade cycles are complex and often require cluster recreation

2. **Team Readiness**
   - No existing Kubernetes production workloads
   - Team has limited K8s experience (would require 2-3 weeks ramp-up)
   - Kubernetes adds failure modes that aren't yet understood

3. **Use Case Fit**
   - Current use cases don't require multi-user pipeline orchestration
   - No complex DAGs that exceed Airflow's capabilities
   - Simple CI/CD pipeline for model deployment is sufficient

## Consequences

### Positive
- Faster time to production for new models
- Lower operational overhead
- Team can focus on ML work, not infrastructure
- Easy integration with existing Airflow workflows

### Negative
- Cannot handle complex multi-stage training pipelines natively
- No built-in hyperparameter tuning (can use external tools like Optuna)
- Multi-user collaboration features are limited compared to Kubeflow

## Alternatives Considered

1. **SageMaker Pipelines** - Good for AWS-native teams, but creates vendor lock-in and cost complexity
2. **Vertex AI ML Metadata** - GCP-native, good but less mature than MLflow for open-source flexibility
3. **Kubeflow + MLflow** - Hybrid approach using Kubeflow for training orchestration and MLflow for model registry - viable for future scale

## Migration Path
If the team grows to >10 models in production or develops multi-user pipeline requirements, we can migrate to Kubeflow Pipelines while maintaining MLflow Model Registry as the model store. The architectures are compatible for this hybrid approach.

## Review Schedule
Review in 6 months or when the team grows beyond 5 ML engineers.