# ADR-003: Kafka over Kinesis for Multi-Cloud Event Streaming

## Status
Accepted

## Date
2024-02-01

## Context
The platform needs real-time event streaming for fraud detection use case. Requirements:
- 50k events/minute peak throughput
- Schema registry for data validation
- Cross-cloud portability (potential future GCP migration)
- Exactly-once semantics for transaction processing

## Decision
We will use **Apache Kafka with Confluent Schema Registry** for event streaming, deployed on Kubernetes (EKS/GKE).

## Rationale

### Kafka Selected Because:

1. **Schema Registry Integration**
   - Confluent Schema Registry provides Avro/Protobuf validation
   - Backward/forward compatibility enforcement
   - Schema evolution handling without service restarts
   - Critical for financial transaction validation

2. **Exactly-Once Semantics**
   - Kafka Transactions API provides exactly-once guarantees
   - Idempotent producers prevent duplicate events
   - Consumer group offset management for reliable processing
   - Critical for fraud detection where double-charging is unacceptable

3. **Cross-Cloud Portability**
   - Strimzi operator for Kubernetes deployment on AWS/GCP
   - Consistent configuration across cloud providers
   - No vendor-specific APIs for core functionality
   - Future migration path to GCP Vertex AI doesn't require platform rewrite

4. **Operational Maturity**
   - Large ecosystem of monitoring tools (Kafka Manager, Cruise Control)
   - Proven at scale for financial services (LinkedIn, Netflix, Uber)
   - Strong Apache community with 1000+ committers

### Kinesis Rejected Because:

1. **AWS-Only Lock-in**
   - No viable cross-cloud deployment option
   - Data format tied to AWS glue schema registry
   - Migration to GCP would require complete reimplementation

2. **Feature Gaps**
   - No native schema registry (requires custom implementation)
   - Exactly-once requires additional engineering (Kafka Streams needed)
   - Enhanced fan-out limited to 2 consumers per shard

3. **Cost Complexity**
   - Shard-based pricing doesn't scale linearly
   - On-demand mode has 50k events/minute limit per shard
   - Reserved shards for cost optimization require 1-year commitment

## Consequences

### Positive
- Battle-tested at massive scale
- Schema registry integration for data quality
- Cross-cloud portability
- Exactly-once guarantees for financial transactions

### Negative
- Higher operational complexity than Kinesis
- Requires Kubernetes expertise for deployment
   - Strimzi operator adds another component to manage
   - Kafka Connect for external integrations needs separate monitoring

## Alternatives Considered

1. **Kinesis Data Streams** - Only viable for AWS-only shops prioritizing operational simplicity
2. **Google Pub/Sub** - Good GCP-native option, but same lock-in as Kinesis
3. **Redpanda** - Interesting modern alternative, less mature but better performance; worth revisiting in 6 months

## Capacity Planning

| Metric | Value |
|--------|-------|
| Peak Throughput | 50k events/min |
| Avg Message Size | 2KB |
| Retention | 7 days |
| Partitions | 24 (3x peak to handle bursts) |
| Replication Factor | 3 |
| Schema Registry | 3 Confluent instances (HA) |

## Review Schedule
Review in 6 months or when Redpanda demonstrates production stability at similar scale.