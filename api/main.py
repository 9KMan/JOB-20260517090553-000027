from flask import Flask, jsonify, request
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import uuid

app = Flask(__name__)


class Model:
    def __init__(self, id: str, name: str, version: str, stage: str, created_at: datetime, metrics: Dict):
        self.id = id
        self.name = name
        self.version = version
        self.stage = stage
        self.created_at = created_at
        self.metrics = metrics

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'version': self.version,
            'stage': self.stage,
            'created_at': self.created_at.isoformat(),
            'metrics': self.metrics
        }


class PipelineRun:
    def __init__(self, id: str, dag_id: str, state: str, started_at: datetime,
                 completed_at: Optional[datetime], error_msg: Optional[str]):
        self.id = id
        self.dag_id = dag_id
        self.state = state
        self.started_at = started_at
        self.completed_at = completed_at
        self.error_msg = error_msg

    def to_dict(self):
        return {
            'id': self.id,
            'dag_id': self.dag_id,
            'state': self.state,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_msg': self.error_msg
        }


models_db: List[Model] = [
    Model('m1', 'fraud-detection', 'v23', 'Production', datetime.now() - timedelta(days=5),
          {'auc': 0.94, 'precision': 0.89, 'recall': 0.87}),
    Model('m2', 'fraud-detection', 'v22', 'Staging', datetime.now() - timedelta(days=12),
          {'auc': 0.93, 'precision': 0.88, 'recall': 0.85}),
    Model('m3', 'customer-churn', 'v5', 'Production', datetime.now() - timedelta(days=3),
          {'auc': 0.91, 'precision': 0.85, 'recall': 0.82}),
    Model('m4', 'recommendation-engine', 'v11', 'Archived', datetime.now() - timedelta(days=45),
          {'auc': 0.88, 'precision': 0.80, 'recall': 0.78}),
]

pipelines_db: Dict[str, List[PipelineRun]] = {
    'etl_spark_batch': [
        PipelineRun('r1', 'etl_spark_batch', 'success', datetime.now() - timedelta(hours=2),
                    datetime.now() - timedelta(hours=1), None),
        PipelineRun('r2', 'etl_spark_batch', 'success', datetime.now() - timedelta(days=1),
                    datetime.now() - timedelta(days=1, hours=-1), None),
        PipelineRun('r3', 'etl_spark_batch', 'failed', datetime.now() - timedelta(days=2),
                    datetime.now() - timedelta(days=2, hours=-2), 'Spark OOM error'),
    ],
    'dbt_transformation': [
        PipelineRun('r4', 'dbt_transformation', 'success', datetime.now() - timedelta(hours=6),
                    datetime.now() - timedelta(hours=5), None),
    ],
    'ml_model_training': [
        PipelineRun('r5', 'ml_model_training', 'running', datetime.now() - timedelta(minutes=30),
                    None, None),
    ],
    'etl_kafka_flink': [
        PipelineRun('r6', 'etl_kafka_flink', 'success', datetime.now() - timedelta(minutes=15),
                    datetime.now() - timedelta(minutes=14), None),
    ],
}

drift_data: Dict[str, List[Dict]] = {
    'm1': [
        {'feature': 'transaction_amount', 'metric': 'psi', 'value': 0.08, 'threshold': 0.2, 'violation': False},
        {'feature': 'customer_age', 'metric': 'ks', 'value': 0.12, 'threshold': 0.15, 'violation': False},
        {'feature': 'country_code', 'metric': 'psi', 'value': 0.18, 'threshold': 0.2, 'violation': False},
        {'feature': 'device_type', 'metric': 'psi', 'value': 0.22, 'threshold': 0.2, 'violation': True},
    ],
    'm3': [
        {'feature': 'session_duration', 'metric': 'ks', 'value': 0.09, 'threshold': 0.15, 'violation': False},
        {'feature': 'page_views', 'metric': 'psi', 'value': 0.11, 'threshold': 0.2, 'violation': False},
    ]
}

alerts_db: List[Dict] = [
    {'id': 'a1', 'type': 'feature_drift', 'severity': 'warning', 'model_id': 'm1',
     'message': 'Drift violation detected in device_type feature', 'triggered_at': datetime.now().isoformat()},
    {'id': 'a2', 'type': 'pipeline_failure', 'severity': 'critical', 'dag_id': 'etl_spark_batch',
     'message': 'Spark OOM on cluster j-12345', 'triggered_at': (datetime.now() - timedelta(hours=2)).isoformat()},
]

slos = [
    {'name': 'MLflow API Latency', 'target': 200, 'current': 145, 'unit': 'ms', 'slo': 99.9},
    {'name': 'SageMaker Endpoint Availability', 'target': 99.95, 'current': 99.97, 'unit': '%', 'slo': 99.95},
    {'name': 'Pipeline Success Rate', 'target': 99.0, 'current': 98.5, 'unit': '%', 'slo': 99.0},
    {'name': 'Data Freshness', 'target': 3600, 'current': 2800, 'unit': 'seconds', 'slo': 99.5},
]


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})


@app.route('/ml/models', methods=['GET'])
def list_models():
    stage_filter = request.args.get('stage')
    filtered_models = models_db
    if stage_filter:
        filtered_models = [m for m in models_db if m.stage.lower() == stage_filter.lower()]

    return jsonify({
        'models': [m.to_dict() for m in filtered_models],
        'total': len(filtered_models)
    })


@app.route('/ml/models/<model_id>', methods=['GET'])
def get_model(model_id: str):
    model = next((m for m in models_db if m.id == model_id), None)
    if not model:
        return jsonify({'error': 'Model not found'}), 404
    return jsonify(model.to_dict())


@app.route('/ml/models/<model_id>/stage', methods=['POST'])
def promote_model_stage(model_id: str):
    model = next((m for m in models_db if m.id == model_id), None)
    if not model:
        return jsonify({'error': 'Model not found'}), 404

    data = request.get_json()
    new_stage = data.get('stage')

    valid_stages = ['Staging', 'Production', 'Archived']
    if new_stage not in valid_stages:
        return jsonify({'error': f'Invalid stage. Must be one of: {valid_stages}'}), 400

    old_stage = model.stage
    model.stage = new_stage

    return jsonify({
        'success': True,
        'model_id': model_id,
        'old_stage': old_stage,
        'new_stage': new_stage,
        'message': f'Model {model_id} promoted from {old_stage} to {new_stage}'
    })


@app.route('/ml/drift/<model_id>', methods=['GET'])
def get_drift_scores(model_id: str):
    drift = drift_data.get(model_id, [])
    if not drift:
        return jsonify({'error': 'No drift data for model'}), 404

    return jsonify({
        'model_id': model_id,
        'drift_scores': drift,
        'summary': {
            'total_features': len(drift),
            'violations': sum(1 for d in drift if d['violation']),
            'max_drift': max((d['value'] for d in drift), default=0)
        }
    })


@app.route('/pipelines', methods=['GET'])
def list_pipelines():
    return jsonify({
        'pipelines': [
            {'dag_id': dag_id, 'total_runs': len(runs), 'last_run': runs[0].to_dict() if runs else None}
            for dag_id, runs in pipelines_db.items()
        ]
    })


@app.route('/pipelines/<dag_id>', methods=['GET'])
def get_pipeline(dag_id: str):
    if dag_id not in pipelines_db:
        return jsonify({'error': 'Pipeline not found'}), 404

    runs = pipelines_db[dag_id]
    return jsonify({
        'dag_id': dag_id,
        'runs': [r.to_dict() for r in runs],
        'total_runs': len(runs)
    })


@app.route('/pipelines/<dag_id>/trigger', methods=['POST'])
def trigger_pipeline(dag_id: str):
    if dag_id not in pipelines_db:
        return jsonify({'error': 'Pipeline not found'}), 404

    run_id = f'r{uuid.uuid4().hex[:8]}'
    new_run = PipelineRun(run_id, dag_id, 'running', datetime.utcnow(), None, None)
    pipelines_db[dag_id].insert(0, new_run)

    return jsonify({
        'success': True,
        'run_id': run_id,
        'dag_id': dag_id,
        'state': 'running',
        'started_at': new_run.started_at.isoformat()
    })


@app.route('/pipelines/<dag_id>/runs/<run_id>', methods=['GET'])
def get_run_details(dag_id: str, run_id: str):
    if dag_id not in pipelines_db:
        return jsonify({'error': 'Pipeline not found'}), 404

    run = next((r for r in pipelines_db[dag_id] if r.id == run_id), None)
    if not run:
        return jsonify({'error': 'Run not found'}), 404

    logs_url = f'https://airflow.example.com/logs/{dag_id}/{run_id}'
    return jsonify({
        **run.to_dict(),
        'logs_url': logs_url
    })


@app.route('/observability/slos', methods=['GET'])
def get_slos():
    return jsonify({
        'slos': slos,
        'generated_at': datetime.utcnow().isoformat()
    })


@app.route('/observability/alerts', methods=['GET'])
def get_alerts():
    severity_filter = request.args.get('severity')
    filtered_alerts = alerts_db
    if severity_filter:
        filtered_alerts = [a for a in alerts_db if a['severity'] == severity_filter.lower()]

    return jsonify({
        'alerts': filtered_alerts,
        'total': len(filtered_alerts)
    })


@app.route('/observability/metrics', methods=['GET'])
def get_metrics():
    metrics = {
        'golden_signals': {
            'latency': {'p50': 45, 'p95': 120, 'p99': 180, 'unit': 'ms'},
            'traffic': {'requests_per_min': 12500, 'error_rate': 0.002},
            'errors': {'4xx_rate': 0.001, '5xx_rate': 0.001},
            'saturation': {'cpu_utilization': 0.65, 'memory_utilization': 0.72}
        },
        'infrastructure': {
            'aws': {'emr_clusters': 3, 'sagemaker_endpoints': 4, 'eks_nodes': 12},
            'gcp': {'mlflow_instances': 1, 'bigquery_slots': 500}
        },
        'generated_at': datetime.utcnow().isoformat()
    }
    return jsonify(metrics)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)