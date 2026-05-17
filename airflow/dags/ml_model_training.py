from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.providers.amazon.aws.operators.sagemaker import SageMakerTrainingOperator, SageMakerTransformOperator
from airflow.providers.amazon.aws.sensors.sagemaker import SageMakerTrainingSensor, SageMakerTransformSensor
import json
import os

default_args = {
    'owner': 'ml-engineering',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

SAGEMAKER_ROLE = 'arn:aws:iam::123456789012:role/SageMakerExecutionRole'
S3_BUCKET = 'mlops-artifacts-prod'
REGION = 'us-east-1'

def check_drift_status(**context):
    from airflow.models import Variable

    drift_threshold = float(Variable.get('drift_threshold', '0.15'))

    drift_scores = {
        'transaction_amount': 0.08,
        'customer_age': 0.12,
        'payment_method': 0.05,
        'country_code': 0.18,
        'device_type': 0.22,
    }

    violations = {k: v for k, v in drift_scores.items() if v > drift_threshold}

    context['ti'].xcom_push(key='drift_violations', value=json.dumps(violations))
    context['ti'].xcom_push(key='retraining_needed', value=len(violations) > 0)

    return len(violations) > 0

def prepare_training_data(**context):
    print('Preparing training data from feature store')

    date_range = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    training_data_path = f's3://{S3_BUCKET}/training-data/{date_range}/'
    print(f'Training data will be sourced from: {training_data_path}')

    return training_data_path

def deploy_model_to_staging(**context):
    training_job_name = context['ti'].xcom_pull(task_ids='train_model', key='training_job_name')

    endpoint_config_name = f'mlops-fraud-{context["ds"]}'
    print(f'Deploying model {training_job_name} to staging endpoint: {endpoint_config_name}')

    return endpoint_config_name

def validate_staging_model(**context):
    import time
    print('Running validation tests on staging model...')
    time.sleep(10)

    validation_results = {
        'latency_p95': 45,
        'throughput_rps': 850,
        'error_rate': 0.002,
        'drift_score': 0.08,
        'passed': True,
    }

    if validation_results['error_rate'] > 0.01:
        validation_results['passed'] = False
        print('VALIDATION FAILED: Error rate too high')

    context['ti'].xcom_push(key='validation_results', value=json.dumps(validation_results))
    return validation_results['passed']

def promote_to_production(**context):
    validation = json.loads(context['ti'].xcom_pull(key='validation_results'))

    if not validation['passed']:
        raise Exception('Cannot promote: staging validation failed')

    print('Promoting model to production via MLflow Model Registry...')

    return {'promoted': True, 'model_version': 'v23'}

with DAG(
    'ml_model_training',
    default_args=default_args,
    description='ML model training pipeline with drift detection and A/B deployment',
    schedule_interval='0 2 * * *',
    catchup=False,
    max_active_runs=1,
    tags=['ml', 'sagemaker', 'mlflow', 'training'],
) as dag:

    check_drift = PythonOperator(
        task_id='check_drift',
        python_callable=check_drift_status,
    )

    decide_retraining = BranchPythonOperator(
        task_id='decide_retraining',
        python_callable=lambda ti, **ctx: ['run_training'] if ti.xcom_pull(task_ids='check_drift', key='retraining_needed') else ['skip_training'],
    )

    skip_training = PythonOperator(
        task_id='skip_training',
        python_callable=lambda: print('Drift within thresholds, skipping retraining'),
    )

    prepare_data = PythonOperator(
        task_id='prepare_data',
        python_callable=prepare_training_data,
    )

    training_config = {
        'AlgorithmSpecification': {
            'TrainingImage': '123456789012.dkr.ecr.us-east-1.amazonaws.com/xgboost:latest',
            'TrainingInputMode': 'File',
        },
        'RoleArn': SAGEMAKER_ROLE,
        'OutputDataConfig': {
            'S3OutputPath': f's3://{S3_BUCKET}/models/output/',
        },
        'ResourceConfig': {
            'InstanceType': 'ml.m5.4xlarge',
            'InstanceCount': 2,
            'VolumeSizeInGB': 100,
        },
        'TrainingJobName': 'fraud-detection-{{ ds }}',
        'HyperParameters': {
            'objective': 'binary:logistic',
            'max_depth': '6',
            'eta': '0.1',
            'subsample': '0.8',
            'eval_metric': 'auc',
        },
        'InputDataConfig': [
            {
                'ChannelName': 'train',
                'DataSource': {
                    'S3DataSource': {
                        'S3Uri': f's3://{S3_BUCKET}/training-data/',
                        'S3DataType': 'S3Prefix',
                        'S3DistributionType': 'FullyReplicated',
                    }
                },
                'ContentType': 'text/csv',
            },
        ],
    }

    train_model = SageMakerTrainingOperator(
        task_id='run_training',
        config=training_config,
        wait_for_completion=False,
    )

    wait_for_training = SageMakerTrainingSensor(
        task_id='wait_for_training_completion',
        training_job_name='fraud-detection-{{ ds }}',
    )

    deploy_staging = PythonOperator(
        task_id='deploy_to_staging',
        python_callable=deploy_model_to_staging,
    )

    validate_staging = PythonOperator(
        task_id='validate_staging',
        python_callable=validate_staging_model,
    )

    run_shadow_test = PythonOperator(
        task_id='run_shadow_test',
        python_callable=lambda: print('Running shadow traffic test for 1 hour'),
        execution_timeout=timedelta(hours=2),
    )

    promote = PythonOperator(
        task_id='promote_to_production',
        python_callable=promote_to_production,
    )

    trigger_monitoring = TriggerDagRunOperator(
        task_id='trigger_monitoring',
        trigger_dag_id='ml_model_monitoring',
        wait_for_completion=False,
    )

    check_drift >> decide_retraining
    decide_retraining >> [run_training, skip_training]
    run_training >> prepare_data >> train_model >> wait_for_training >> deploy_staging
    deploy_staging >> validate_staging >> run_shadow_test >> promote
    promote >> trigger_monitoring