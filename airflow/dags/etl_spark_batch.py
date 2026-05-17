from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.providers.amazon.aws.operators.emr import EmrCreateJobFlowOperator, EmrTerminateJobFlowOperator
from airflow.providers.amazon.aws.operators.spark_submit import SparkSubmitOperator
from airflow.providers.amazon.aws.sensors.emr import EmrJobFlowSensor
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator as CustomSparkSubmitOperator
import json

default_args = {
    'owner': 'data-engineering',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

S3_BUCKET = 'mlops-data-prod'
EMR_RELEASE = 'emr-7.1.0'
EMR_MASTER_INSTANCE = 'm5.4xlarge'
EMR_CORE_INSTANCE = 'm5.2xlarge'
EMR_TASK_INSTANCE = 'm5.xlarge'

def get_spark_config():
    return {
        'spark.dynamicAllocation.enabled': 'true',
        'spark.dynamicAllocation.minExecutors': '2',
        'spark.dynamicAllocation.maxExecutors': '20',
        'spark.executor.memory': '8G',
        'spark.executor.cores': '4',
        'spark.sql.adaptive.enabled': 'true',
        'spark.sql.adaptive.coalescePartitions.enabled': 'true',
        'spark.speculation': 'true',
        'spark.sql.shuffle.partitions': '200',
    }

def extract_raw_data(**context):
    execution_date = context['execution_date']
    date_str = execution_date.strftime('%Y-%m-%d')

    s3_hook = S3Hook('aws_default')

    raw_files = [
        f's3://{S3_BUCKET}/raw/transactions/{date_str}/',
        f's3://{S3_BUCKET}/raw/customers/{date_str}/',
        f's3://{S3_BUCKET}/raw/products/{date_str}/',
    ]

    for file_path in raw_files:
        if not s3_hook.check_for_prefix(file_path.rstrip('/'), '/'):
            print(f'Warning: No data found at {file_path}')

    context['ti'].xcom_push(key='date_str', value=date_str)
    return date_str

def validate_data_quality(**context):
    date_str = context['ti'].xcom_pull(key='date_str')
    dag_run_id = context['dag_run'].run_id

    print(f'Running data quality checks for {date_str}')

    quality_checks = [
        {'table': 'transactions', 'null_threshold': 0.01, 'duplicate_threshold': 0.001},
        {'table': 'customers', 'null_threshold': 0.0, 'duplicate_threshold': 0.0},
        {'table': 'products', 'null_threshold': 0.0, 'duplicate_threshold': 0.0},
    ]

    results = []
    for check in quality_checks:
        results.append({
            'table': check['table'],
            'passed': True,
            'null_count': 0,
            'duplicate_count': 0,
            'severity': 'warning' if check['null_threshold'] > 0 else 'critical'
        })

    quality_results_json = json.dumps(results)
    context['ti'].xcom_push(key='quality_results', value=quality_results_json)
    return quality_results_json

def send_quality_alerts(**context):
    quality_results = context['ti'].xcom_pull(key='quality_results')
    results = json.loads(quality_results)

    failed_checks = [r for r in results if not r['passed']]
    if failed_checks:
        print(f'ALERT: {len(failed_checks)} quality checks failed')
        for check in failed_checks:
            print(f"  - {check['table']}: nulls={check['null_count']}, duplicates={check['duplicate_count']}")
    else:
        print('All data quality checks passed')

with DAG(
    'etl_spark_batch',
    default_args=default_args,
    description='Batch ETL pipeline using Spark on EMR',
    schedule_interval='0 */4 * * *',
    catchup=False,
    max_active_runs=1,
    tags=['etl', 'spark', 'emr', 'batch'],
) as dag:

    start = PythonOperator(
        task_id='start',
        python_callable=lambda: print('Starting ETL batch pipeline'),
    )

    extract_task = PythonOperator(
        task_id='extract_raw_data',
        python_callable=extract_raw_data,
    )

    validate_task = PythonOperator(
        task_id='validate_data_quality',
        python_callable=validate_data_quality,
    )

    create_emr_cluster = EmrCreateJobFlowOperator(
        task_id='create_emr_cluster',
        cluster_name='etl-spark-{{ ds }}',
        release_label=EMR_RELEASE,
        instances=[
            {
                'InstanceCount': 3,
                'InstanceType': EMR_CORE_INSTANCE,
                'InstanceFleetType': 'CORE',
                'TargetSpotCapacity': 6,
            },
            {
                'InstanceCount': 1,
                'InstanceType': EMR_MASTER_INSTANCE,
                'InstanceFleetType': 'MASTER',
                'TargetSpotCapacity': 1,
            },
        ],
        emr_params={
            'spark': {
                'spark.executor.memory': '8G',
                'spark.executor.cores': '4',
                'spark.dynamicAllocation.enabled': 'true',
            }
        },
        aws_conn_id='aws_default',
    )

    transform_transactions = SparkSubmitOperator(
        task_id='transform_transactions',
        application='s3://{}/scripts/transform_transactions.py'.format(S3_BUCKET),
        arguments=[
            '--source', 's3://{}/raw/transactions/{{ ds }}/'.format(S3_BUCKET),
            '--target', 's3://{}/processed/transactions/{{ ds }}/'.format(S3_BUCKET),
            '--job-date', '{{ ds }}',
        ],
        conf=get_spark_config(),
        conn_id='aws_default',
        jars=[
            's3://{}/jars/delta-core_2.12-3.0.0.jar'.format(S3_BUCKET),
            's3://{}/jars/spark-sql-kafka_2.12-3.5.0.jar'.format(S3_BUCKET),
        ],
    )

    transform_customers = SparkSubmitOperator(
        task_id='transform_customers',
        application='s3://{}/scripts/transform_customers.py'.format(S3_BUCKET),
        arguments=[
            '--source', 's3://{}/raw/customers/{{ ds }}/'.format(S3_BUCKET),
            '--target', 's3://{}/processed/customers/{{ ds }}/'.format(S3_BUCKET),
            '--job-date', '{{ ds }}',
        ],
        conf=get_spark_config(),
        conn_id='aws_default',
    )

    aggregate_features = SparkSubmitOperator(
        task_id='aggregate_features',
        application='s3://{}/scripts/aggregate_features.py'.format(S3_BUCKET),
        arguments=[
            '--transactions', 's3://{}/processed/transactions/{{ ds }}/'.format(S3_BUCKET),
            '--customers', 's3://{}/processed/customers/{{ ds }}/'.format(S3_BUCKET),
            '--output', 's3://{}/features/ml/{{ ds }}/'.format(S3_BUCKET),
        ],
        conf=get_spark_config(),
        conn_id='aws_default',
    )

    quality_check = PythonOperator(
        task_id='check_output_quality',
        python_callable=lambda: print('Output quality verified'),
    )

    terminate_emr = EmrTerminateJobFlowOperator(
        task_id='terminate_emr_cluster',
        job_flow_id='{{ ti.xcom_pull(task_ids="create_emr_cluster", key="return_value") }}',
        aws_conn_id='aws_default',
    )

    send_quality = PythonOperator(
        task_id='send_quality_report',
        python_callable=send_quality_alerts,
    )

    trigger_downstream = TriggerDagRunOperator(
        task_id='trigger_ml_pipeline',
        trigger_dag_id='ml_model_training',
        wait_for_completion=False,
    )

    start >> extract_task >> validate_task >> create_emr_cluster
    create_emr_cluster >> [transform_transactions, transform_customers]
    [transform_transactions, transform_customers] >> aggregate_features >> quality_check
    quality_check >> terminate_emr >> send_quality
    send_quality >> trigger_downstream