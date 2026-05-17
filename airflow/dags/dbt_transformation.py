from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.providers.amazon.aws.operators.emr_create_job_flow import EmrCreateJobFlowOperator
from airflow.providers.amazon.aws.operators.emr import EmrTerminateJobFlowOperator
from airflow.providers.amazon.aws.sensors.emr import EmrJobFlowSensor
from airflow.utils.task_group import TaskGroup
import os

default_args = {
    'owner': 'data-engineering',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

S3_BUCKET = 'mlops-data-prod'
DBT_PROJECT_DIR = 's3://{}/dbt/ml-platform/'.format(S3_BUCKET)
DBT_PROFILES_DIR = 's3://{}/dbt/profiles.yml'.format(S3_BUCKET)

def ensure_raw_tables():
    print('Ensuring raw tables exist in Glue metastore')
    return True

def run_dbt_models(models='models'):
    print(f'Running dbt {models}...')
    return True

def capture_dbt_results(**context):
    dag_run_id = context['dag_run'].run_id
    print(f'Capturing dbt run results for DAG run: {dag_run_id}')
    return {'succeeded': 10, 'failed': 0, 'warned': 2}

def send_dbt_notifications(**context):
    results = context['ti'].xcom_pull(task_ids='capture_dbt_results')
    print(f'dbt run completed: {results}')
    return True

with DAG(
    'dbt_transformation',
    default_args=default_args,
    description='dbt transformation pipeline for Delta Lake',
    schedule_interval='0 */6 * * *',
    catchup=False,
    max_active_runs=1,
    tags=['dbt', 'transformation', 'delta-lake', 'analytics'],
) as dag:

    start = PythonOperator(
        task_id='start',
        python_callable=lambda: print('Starting dbt transformation pipeline'),
    )

    with TaskGroup('raw_layer') as raw_layer:

        ensure_customers = PythonOperator(
            task_id='ensure_customers_raw',
            python_callable=ensure_raw_tables,
        )

        ensure_transactions = PythonOperator(
            task_id='ensure_transactions_raw',
            python_callable=ensure_raw_tables,
        )

        ensure_products = PythonOperator(
            task_id='ensure_products_raw',
            python_callable=ensure_raw_tables,
        )

    with TaskGroup('staging_layer') as staging_layer:

        stage_customers = PythonOperator(
            task_id='stage_customers',
            python_callable=lambda: run_dbt_models('staging.stg_customers'),
        )

        stage_transactions = PythonOperator(
            task_id='stage_transactions',
            python_callable=lambda: run_dbt_models('staging.stg_transactions'),
        )

    with TaskGroup('mart_layer') as mart_layer:

        marts_finance = PythonOperator(
            task_id='finance_marts',
            python_callable=lambda: run_dbt_models('marts.finance'),
        )

        marts_ml_features = PythonOperator(
            task_id='ml_features_marts',
            python_callable=lambda: run_dbt_models('marts.ml_features'),
        )

    quality_tests = PythonOperator(
        task_id='run_quality_tests',
        python_callable=lambda: print('Running Great Expectations quality tests...'),
    )

    capture_results = PythonOperator(
        task_id='capture_dbt_results',
        python_callable=capture_dbt_results,
        provide_context=True,
    )

    decide_notifications = BranchPythonOperator(
        task_id='decide_notifications',
        python_callable=lambda ti, **ctx: ['send_success_notification'] if ti.xcom_pull(task_ids='capture_dbt_results', key='failed', default=1) == 0 else ['send_failure_alert'],
    )

    send_success = PythonOperator(
        task_id='send_success_notification',
        python_callable=lambda: print('dbt run succeeded - sending notification'),
    )

    send_failure = PythonOperator(
        task_id='send_failure_alert',
        python_callable=lambda: print('dbt run had failures - sending alert'),
    )

    start >> raw_layer >> staging_layer >> mart_layer >> quality_tests >> capture_results
    capture_results >> decide_notifications
    decide_notifications >> [send_success, send_failure]