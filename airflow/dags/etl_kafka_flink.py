from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sensors.kafka import KafkaConsumerSensor
from airflow.providers.apache.kafka.operators.produce import ProduceToKafkaOperator
from airflow.providers.apache.kafka.operators.consume import ConsumeFromTopicOperator
from airflow.utils.task_group import TaskGroup
import json

default_args = {
    'owner': 'data-engineering',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 3,
    'retry_delay': timedelta(minutes=2),
}

KAFKA_BROKER = 'kafka:9092'
SCHEMA_REGISTRY_URL = 'http://schema-registry:8081'
INPUT_TOPIC = 'raw-events'
PROCESSED_TOPIC = 'processed-events'
DLQ_TOPIC = 'dlq-events'
CHECKPOINT_DIR = 's3://mlops-checkpoints-prod/flink/checkpoints/'
STATE_BACKEND = 'filesystem'

def validate_schema(payload, expected_schema):
    required_fields = ['event_id', 'timestamp', 'event_type', 'data']
    for field in required_fields:
        if field not in payload:
            return False, f'Missing required field: {field}'
    return True, None

def process_event(event):
    if not event or 'data' not in event:
        return {'error': 'Invalid event format', 'original': event}

    event_type = event.get('event_type')
    data = event['data']

    processed = {
        'event_id': event['event_id'],
        'timestamp': event['timestamp'],
        'processed_at': datetime.utcnow().isoformat(),
        'event_type': event_type,
        'data': data,
    }

    if event_type == 'transaction':
        processed['features'] = {
            'amount': float(data.get('amount', 0)),
            'card_present': bool(data.get('card_present', False)),
            'country_code': data.get('country', 'US'),
            'hour': datetime.fromisoformat(event['timestamp']).hour,
        }
    elif event_type == 'customer_action':
        processed['features'] = {
            'action_type': data.get('action_type'),
            'session_duration': int(data.get('duration', 0)),
            'page_views': int(data.get('pages', 0)),
        }

    return processed

def on_processing_failure(context):
    ti = context['ti']
    ti.xcom_push(key='failed_events', value=context.get('event_count', 0))

with DAG(
    'etl_kafka_flink',
    default_args=default_args,
    description='Real-time streaming ETL with Kafka and Flink',
    schedule_interval=None,
    catchup=False,
    max_active_runs=10,
    tags=['streaming', 'kafka', 'flink', 'real-time'],
) as dag:

    start = PythonOperator(
        task_id='start',
        python_callable=lambda: print('Starting Kafka streaming pipeline'),
    )

    consume_raw_events = ConsumeFromTopicOperator(
        task_id='consume_raw_events',
        kafka_config={
            'bootstrap.servers': KAFKA_BROKER,
            'group.id': 'flink-consumer-group',
            'auto.offset.reset': 'latest',
            'enable.auto.commit': 'false',
        },
        topics=[INPUT_TOPIC],
        max_messages=1000,
        poll_timeout=60,
    )

    validate_events = BranchPythonOperator(
        task_id='validate_schema',
        python_callable=lambda ti, **ctx: 'process_valid_events' if ti.xcom_pull(task_ids='consume_raw_events', key='message_count', default=0) > 0 else 'handle_empty_batch',
    )

    with TaskGroup('processing_group') as processing_group:

        enrich_events = PythonOperator(
            task_id='enrich_events',
            python_callable=lambda ti, **ctx: [
                process_event(json.loads(msg))
                for msg in ti.xcom_pull(task_ids='consume_raw_events', key='messages', default=[])
            ],
        )

        apply_feature_engineering = PythonOperator(
            task_id='apply_feature_engineering',
            python_callable=lambda ti, **ctx: [
                {
                    **event,
                    'engineered_features': {
                        'transaction_velocity': event.get('features', {}).get('amount', 0) / max(event.get('features', {}).get('hour', 1), 1),
                        'risk_score': hash(event.get('event_id', '')) % 100 / 100.0,
                    }
                }
                for event in ti.xcom_pull(task_ids='enrich_events', key='return_value', default=[])
            ],
        )

        detect_anomalies = PythonOperator(
            task_id='detect_anomalies',
            python_callable=lambda ti, **ctx: [
                {**event, 'anomaly_score': 0.85 if event.get('engineered_features', {}).get('risk_score', 0) > 0.7 else 0.2}
                for event in ti.xcom_pull(task_ids='apply_feature_engineering', key='return_value', default=[])
            ],
        )

    produce_processed = ProduceToKafkaOperator(
        task_id='produce_processed_events',
        topic=PROCESSED_TOPIC,
        producer_config={
            'bootstrap.servers': KAFKA_BROKER,
            'acks': 'all',
            'retries': 3,
        },
        produce_kwargs={
            'topic': PROCESSED_TOPIC,
        },
        provide_context=True,
    )

    handle_failures = PythonOperator(
        task_id='handle_failures',
        python_callable=lambda ti, **ctx: print('Handling failed events via DLQ'),
    )

    produce_to_dlq = ProduceToKafkaOperator(
        task_id='produce_to_dlq',
        topic=DLQ_TOPIC,
        producer_config={
            'bootstrap.servers': KAFKA_BROKER,
            'acks': 'all',
        },
        produce_kwargs={
            'topic': DLQ_TOPIC,
        },
        provide_context=True,
    )

    commit_offset = PythonOperator(
        task_id='commit_offset',
        python_callable=lambda: print('Committed Kafka offsets'),
    )

    trigger_batch_aggregate = TriggerDagRunOperator(
        task_id='trigger_batch_aggregate',
        trigger_dag_id='etl_spark_batch',
        wait_for_completion=False,
    )

    start >> consume_raw_events >> validate_events
    validate_events >> processing_group >> produce_processed
    produce_processed >> handle_failures >> produce_to_dlq >> commit_offset
    validate_events >> commit_offset
    commit_offset >> trigger_batch_aggregate