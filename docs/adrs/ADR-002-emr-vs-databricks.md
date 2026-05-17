# ADR-002: EMR for Batch Spark Workloads over Databricks

## Status
Accepted

## Date
2024-01-20

## Context
The data platform needs to process large batch ETL workloads (15-20TB daily). Current workload profile:
- 40+ Airflow DAGs running daily
- 200+ Spark jobs per day
- Heavy use of Delta Lake for data storage
- Cost-sensitive organization with $15k/month cloud budget

## Decision
We will use **Amazon EMR (Elastic MapReduce) with Spark** for batch processing workloads, with Spot instances for task nodes to optimize cost.

## Rationale

### EMR Selected Because:

1. **Cost Optimization**
   - Spot instances for task nodes (60-70% savings vs. on-demand)
   - EMR on EC2 vs. Databricks private endpoint pricing
   - Auto-termination of clusters after idle timeout (15 min default)
   - Reserved instances for master/core nodes to cap baseline costs
   - Estimated savings: $8-10k/month vs. equivalent Databricks setup

2. **Operational Flexibility**
   - Full control over cluster configuration
   - Custom bootstrap actions for environment setup
   - Fine-grained IAM policies per use case
   - Integration with existing S3 data lake architecture

3. **Integration with Existing Stack**
   - Airflow operators (apache-airflow-providers-amazon) support EMR natively
   - Spark History Server accessible for debugging
   - Integration with Glue Data Catalog for metastore
   - Terraform modules already exist for EMR in the organization

### Databricks Rejected Because:

1. **Cost Structure**
   - Databricks Unit (DBU) pricing adds significant overhead
   - Minimum cluster configuration requirements
   - Premium tier required for Unity Catalog (~$0.20/DBU)
   - Cost estimates: 2-3x EMR for equivalent workload

2. **Vendor Lock-in**
   - Delta Lake format is great but creates Databricks dependency
   - Notebook-based development doesn't fit CI/CD workflows
   - Job scheduling tied to Databricks workspace

3. **Feature Overlap**
   - Airflow already handles orchestration well
   - dbt handles SQL transformations better than Spark SQL
   - MLflow can replace Databricks experiments UI

## Consequences

### Positive
- Significant cost reduction for batch workloads
- Full control over Spark configuration
- Integration with existing Airflow workflows
- Avoid vendor lock-in for data storage format

### Negative
- More operational overhead than managed Databricks
- Requires careful Spot instance management
- Manual cluster sizing decisions

## Alternatives Considered

1. **EMR Serverless** - Good option for variable workloads, pricing still uncertain at time of decision
2. **Glue** - Insufficient for heavy ETL, better as complement for smaller jobs
3. **Databricks** - Viable if cost constraints are removed, recommended for teams prioritizing developer experience

## Cost Comparison

| Component | EMR | Databricks |
|-----------|-----|------------|
| Compute | $6k (Spot) + $2k (On-demand) | $12k |
| Storage | Included in EC2 cost | $3k (DBU) |
| Metastore | $200 (Glue) | $500 (Unity Catalog) |
| **Total** | **~$8.5k/month** | **~$15.5k/month** |

## Review Schedule
Review in 3 months or if EMR Serverless pricing becomes competitive.