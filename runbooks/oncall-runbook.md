# On-Call Runbook: MLOps Platform

## Incident Response Matrix

| Severity | Response Time | Example |
|----------|---------------|---------|
| P1 Critical | 15 min | Model endpoint down, data pipeline failure |
| P2 High | 30 min | High latency, drift alert |
| P3 Medium | 2 hours | Non-critical DAG failures, minor drift |
| P4 Low | Next business day | Documentation updates, minor improvements |

## Common Incidents

### 1. MLflow Server Unreachable

**Symptoms:**
- `curl http://mlflow-server:8000` fails
- Airflow DAG fails with "MLflow connection error"
- Model registration fails

**Diagnosis:**
```bash
# Check MLflow process
ssh mlflow-server
systemctl status mlflow
journalctl -u mlflow -n 50

# Check resource usage
top -c
df -h
free -m

# Check database connectivity
psql -h $DB_HOST -U mlflow_admin -d mlflow
```

**Fix:**
```bash
# Restart MLflow service
systemctl restart mlflow

# If database connection issue
pg_isready -h $DB_HOST -p 5432

# Check disk space - clean up if needed
du -sh /var/log/mlflow/*
```

**Escalation:**
- If not resolved in 30 minutes, escalate to AWS/GCP infrastructure team
- If database is corrupted, restore from latest backup

---

### 2. SageMaker Endpoint High Latency

**Symptoms:**
- `ModelLatency` metric > 100ms p99
- Customer complaints about API response times

**Diagnosis:**
```bash
# Check CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/SageMaker \
  --metric-name ModelLatency \
  --dimensions Name=EndpointName,Value=$ENDPOINT_NAME \
  --start-time $(date -u -d '1 hour ago') \
  --end-time $(date -u) \
  --period 300 \
  --statistics p99

# Check instance CPU
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID \
  --start-time $(date -u -d '30 min ago') \
  --end-time $(date -u) \
  --period 60
```

**Fix:**
```bash
# Scale up instance count
aws sagemaker update-endpoint \
  --endpoint-name $ENDPOINT_NAME \
  --endpoint-config-name ${ENDPOINT_NAME}-config

# Or change to larger instance type
aws sagemaker update-endpoint-config \
  --endpoint-config-name ${ENDPOINT_NAME}-config \
  --production-variants "[{\"VariantName\": \"AllTraffic\", \
    \"InstanceType\": \"ml.m5.4xlarge\", \"InitialInstanceCount\": 4}]"
```

**Escalation:**
- If latency persists after scaling, check model artifact integrity
- Verify feature preprocessing hasn't changed

---

### 3. EMR Cluster Creation Failure

**Symptoms:**
- `EmrCreateJobFlowOperator` fails
- "Timeout waiting for cluster to be created"

**Diagnosis:**
```bash
# Check EMR console for cluster state
aws emr describe-cluster --cluster-id $CLUSTER_ID

# Check for VPC issues
aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=$VPC_ID"

# Check subnet capacity
aws ec2 describe-subnets --subnet-ids $SUBNET_ID
```

**Fix:**
```bash
# Check IAM roles
aws iam get-role --role-name EMR_DefaultRole
aws iam get-role --role-name EMR_EC2_DefaultRole

# Retry with modified configuration
# Use smaller instance types or different subnet
```

---

### 4. Kafka Consumer Lag

**Symptoms:**
- `kafka_consumer_lag_messages` > 10000
- Events processing behind schedule

**Diagnosis:**
```bash
# Check consumer group status
kafka-consumer-groups.sh --bootstrap-server $KAFKA_BROKER \
  --group flink-consumer-group --describe

# Check partition health
kafka-topics.sh --bootstrap-server $KAFKA_BROKER \
  --describe --topic raw-events

# Check broker disk space
df -h /var/lib/kafka
```

**Fix:**
```bash
# Increase consumer count (if partitioning allows)
# Add more partitions to topic
kafka-topics.sh --alter --topic raw-events \
  --partitions 48 --bootstrap-server $KAFKA_BROKER

# Scale consumer group
# Adjust fetch settings in Flink Kafka connector
```

---

### 5. Data Quality Alert

**Symptoms:**
- `data_quality_score` < 0.95
- Null counts exceed threshold

**Diagnosis:**
```bash
# Check source data freshness
aws s3 ls s3://$BUCKET/raw/transactions/$(date -u -d '1 hour ago' +%Y-%m-%d)/

# Check Great Expectations results
cat /var/log/airflow/ge_results.json | jq '.results[] | select(.success == false)'

# Verify schema validation
python3 -c "
import pandas as pd
df = pd.read_csv('s3://$BUCKET/raw/transactions/latest/part-0000.csv')
print(df.dtypes)
print(df.isnull().sum())
"
```

**Fix:**
```bash
# Re-run data quality checks
airflow trigger_dag -d etl_spark_batch -r "replay_$(date +%Y%m%d%H%M)"

# If schema changed, update Great Expectations expectations
# Send alert to data engineering team for source system investigation
```

---

## Emergency Contacts

| Role | Name | Phone | Slack |
|------|------|-------|-------|
| MLOps Lead | On-call rotation | +1-XXX-XXX-XXXX | #mlops-oncall |
| Data Platform Eng | On-call rotation | +1-XXX-XXX-XXXX | #data-platform-oncall |
| AWS Infrastructure | AWS Support | 1-800-XXX-XXXX | #aws-support |
| Database Admin | On-call rotation | +1-XXX-XXX-XXXX | #dba-oncall |

## Post-Incident Process

1. Create incident in PagerDuty
2. Document timeline in #incidents Slack channel
3. Schedule post-mortem within 48 hours
4. Update runbook if gap found
5. Close incident after 7 days of stability