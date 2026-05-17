import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json
import boto3
import warnings

warnings.filterwarnings('ignore')


@dataclass
class DriftMetric:
    feature_name: str
    metric_name: str
    value: float
    threshold: float
    is_violation: bool
    timestamp: datetime


class DistributionValidator:

    @staticmethod
    def compute_psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
        expected = np.clip(expected, 1e-6, None)
        actual = np.clip(actual, 1e-6, None)

        breakpoints = np.histogram(expected, bins=bins)[1]
        expected_counts = np.histogram(expected, bins=breakpoints)[0]
        actual_counts = np.histogram(actual, bins=breakpoints)[0]

        expected_pct = expected_counts / len(expected)
        actual_pct = actual_counts / len(actual)

        expected_pct = np.clip(expected_pct, 1e-6, None)
        actual_pct = np.clip(actual_pct, 1e-6, None)

        psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
        return psi

    @staticmethod
    def compute_ks_statistic(sample1: np.ndarray, sample2: np.ndarray) -> float:
        sorted1 = np.sort(sample1)
        sorted2 = np.sort(sample2)
        n1, n2 = len(sorted1), len(sorted2)
        cdf1 = np.arange(1, n1 + 1) / n1
        cdf2 = np.arange(1, n2 + 1) / n2
        ks = 0
        i, j = 0, 0
        while i < n1 and j < n2:
            if sorted1[i] < sorted2[j]:
                ks = max(ks, abs(cdf1[i] - (j / n2)))
                i += 1
            else:
                ks = max(ks, abs(cdf1[i] - (j / n2)))
                j += 1
        return ks

    @staticmethod
    def compute_kl_divergence(p: np.ndarray, q: np.ndarray) -> float:
        p = np.clip(p, 1e-10, None)
        q = np.clip(q, 1e-10, None)
        p = p / p.sum()
        q = q / q.sum()
        return np.sum(p * np.log(p / q))


class FeatureDriftDetector:

    def __init__(
        self,
        reference_data: pd.DataFrame,
        feature_columns: List[str],
        psi_threshold: float = 0.2,
        ks_threshold: float = 0.15,
        categorical_features: Optional[List[str]] = None,
    ):
        self.reference_data = reference_data
        self.feature_columns = feature_columns
        self.psi_threshold = psi_threshold
        self.ks_threshold = ks_threshold
        self.categorical_features = categorical_features or []
        self.numerical_features = [c for c in feature_columns if c not in self.categorical_features]

        self.reference_stats = self._compute_reference_stats()

    def _compute_reference_stats(self) -> Dict:
        stats = {}
        for col in self.feature_columns:
            if col in self.categorical_features:
                stats[col] = {
                    'distribution': self.reference_data[col].value_counts(normalize=True).to_dict(),
                    'type': 'categorical'
                }
            else:
                data = self.reference_data[col].dropna().values
                stats[col] = {
                    'mean': np.mean(data),
                    'std': np.std(data),
                    'median': np.median(data),
                    'q25': np.percentile(data, 25),
                    'q75': np.percentile(data, 75),
                    'min': np.min(data),
                    'max': np.max(data),
                    'type': 'numerical'
                }
        return stats

    def compute_feature_drift(
        self,
        current_data: pd.DataFrame,
        feature_name: str
    ) -> DriftMetric:
        ref_stats = self.reference_stats.get(feature_name, {})

        if ref_stats.get('type') == 'categorical':
            ref_dist = ref_stats['distribution']
            curr_dist = current_data[feature_name].value_counts(normalize=True).to_dict()

            all_cats = set(ref_dist.keys()) | set(curr_dist.keys())
            ref_vec = np.array([ref_dist.get(c, 0) for c in all_cats])
            curr_vec = np.array([curr_dist.get(c, 0) for c in all_cats])

            drift_value = DistributionValidator.compute_psi(ref_vec, curr_vec)
            threshold = self.psi_threshold

        else:
            ref_values = self.reference_data[feature_name].dropna().values
            curr_values = current_data[feature_name].dropna().values

            psi = DistributionValidator.compute_psi(ref_values, curr_values)
            ks = DistributionValidator.compute_ks_statistic(ref_values, curr_values)

            drift_value = max(psi, ks)
            threshold = self.ks_threshold

        return DriftMetric(
            feature_name=feature_name,
            metric_name='psi' if ref_stats.get('type') == 'categorical' else 'ks',
            value=drift_value,
            threshold=threshold,
            is_violation=drift_value > threshold,
            timestamp=datetime.utcnow()
        )

    def detect_all_drift(self, current_data: pd.DataFrame) -> List[DriftMetric]:
        drift_results = []
        for feature in self.feature_columns:
            if feature in current_data.columns:
                drift_results.append(self.compute_feature_drift(current_data, feature))
        return drift_results

    def get_violations(self, drift_results: List[DriftMetric]) -> List[DriftMetric]:
        return [d for d in drift_results if d.is_violation]


class PredictionDriftDetector:

    def __init__(
        self,
        reference_predictions: np.ndarray,
        alert_threshold: float = 0.1,
    ):
        self.reference_predictions = reference_predictions
        self.alert_threshold = alert_threshold
        self.reference_mean = np.mean(reference_predictions)
        self.reference_std = np.std(reference_predictions)

    def detect_prediction_drift(
        self,
        current_predictions: np.ndarray
    ) -> Dict[str, any]:
        current_mean = np.mean(current_predictions)
        current_std = np.std(current_predictions)

        mean_shift = abs(current_mean - self.reference_mean) / max(self.reference_std, 1e-10)
        std_ratio = current_std / max(self.reference_std, 1e-10)

        psi = DistributionValidator.compute_psi(
            self.reference_predictions,
            current_predictions
        )

        return {
            'mean_shift_score': mean_shift,
            'std_ratio': std_ratio,
            'psi': psi,
            'alert_triggered': psi > self.alert_threshold,
            'current_mean': current_mean,
            'reference_mean': self.reference_mean,
            'current_std': current_std,
            'reference_std': self.reference_std,
        }


class DriftMonitor:

    def __init__(
        self,
        project_name: str,
        model_name: str,
        s3_bucket: str,
        drift_config: Optional[Dict] = None,
    ):
        self.project_name = project_name
        self.model_name = model_name
        self.s3_bucket = s3_bucket
        self.s3_client = boto3.client('s3')

        self.drift_config = drift_config or {
            'psi_threshold': 0.2,
            'ks_threshold': 0.15,
            'prediction_threshold': 0.1,
        }

        self.feature_detector: Optional[FeatureDriftDetector] = None
        self.prediction_detector: Optional[PredictionDriftDetector] = None

    def load_reference_data(
        self,
        reference_path: str,
        feature_columns: List[str],
        categorical_features: Optional[List[str]] = None
    ):
        if reference_path.startswith('s3://'):
            bucket, key = reference_path.replace('s3://', '').split('/', 1)
            obj = self.s3_client.get_object(Bucket=bucket, Key=key)
            df = pd.read_csv(obj['Body'])
        else:
            df = pd.read_csv(reference_path)

        self.feature_detector = FeatureDriftDetector(
            reference_data=df,
            feature_columns=feature_columns,
            psi_threshold=self.drift_config['psi_threshold'],
            ks_threshold=self.drift_config['ks_threshold'],
            categorical_features=categorical_features,
        )

        return df

    def load_reference_predictions(self, reference_predictions: np.ndarray):
        self.prediction_detector = PredictionDriftDetector(
            reference_predictions=reference_predictions,
            alert_threshold=self.drift_config['prediction_threshold'],
        )

    def run_drift_detection(
        self,
        current_data: pd.DataFrame,
        current_predictions: Optional[np.ndarray] = None
    ) -> Dict:
        results = {
            'model_name': self.model_name,
            'timestamp': datetime.utcnow().isoformat(),
            'feature_drift': [],
            'prediction_drift': None,
            'alerts': []
        }

        if self.feature_detector:
            feature_drift = self.feature_detector.detect_all_drift(current_data)
            results['feature_drift'] = [
                {
                    'feature': d.feature_name,
                    'metric': d.metric_name,
                    'value': float(d.value),
                    'threshold': float(d.threshold),
                    'violation': d.is_violation
                }
                for d in feature_drift
            ]

            violations = self.feature_detector.get_violations(feature_drift)
            if violations:
                results['alerts'].append({
                    'type': 'feature_drift',
                    'severity': 'critical' if len(violations) > 3 else 'warning',
                    'features': [v.feature_name for v in violations],
                    'message': f"Drift violation detected in {len(violations)} features"
                })

        if self.prediction_detector and current_predictions is not None:
            pred_drift = self.prediction_detector.detect_prediction_drift(current_predictions)
            results['prediction_drift'] = pred_drift

            if pred_drift['alert_triggered']:
                results['alerts'].append({
                    'type': 'prediction_drift',
                    'severity': 'warning',
                    'message': f"Prediction distribution shift detected (PSI={pred_drift['psi']:.4f})"
                })

        return results

    def save_drift_report(self, results: Dict):
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        report_key = f"drift-reports/{self.model_name}/{timestamp}_drift_report.json"

        self.s3_client.put_object(
            Bucket=self.s3_bucket,
            Key=report_key,
            Body=json.dumps(results, indent=2)
        )

        return report_key

    def log_to_mlflow(self, results: Dict):
        import mlflow

        with mlflow.start_run(run_name=f"drift-detection-{self.model_name}"):
            mlflow.log_param("model_name", self.model_name)

            for alert in results.get('alerts', []):
                mlflow.log_param(f"alert_{alert['type']}", alert['message'])

            for fd in results.get('feature_drift', []):
                mlflow.log_metric(f"drift_{fd['feature']}_{fd['metric']}", fd['value'])

            if results.get('prediction_drift'):
                pd_data = results['prediction_drift']
                mlflow.log_metric("prediction_psi", pd_data['psi'])
                mlflow.log_metric("prediction_mean_shift", pd_data['mean_shift_score'])


def create_monitoring_schedule(model_name: str, schedule: str = "cron(0 * ? * * *)"):
    return {
        'name': f'{model_name}-drift-monitor',
        'schedule': schedule,
        'input': {
            'feature_data_s3_path': f's3://{{{{ bucket }}/}}/features/{model_name}/latest/',
            'predictions_s3_path': f's3://{{{{ bucket }}/}}/predictions/{model_name}/latest/',
        },
        'output': {
            'drift_reports_s3_path': f's3://{{{{ bucket }}/}}/drift-reports/{model_name}/',
        },
        'alert_config': {
            'sns_topic_arn': 'arn:aws:sns:us-east-1:123456789012:drift-alerts',
            'severity_threshold': 0.2,
        }
    }


if __name__ == '__main__':
    sample_ref_data = pd.DataFrame({
        'transaction_amount': np.random.lognormal(5, 1, 1000),
        'customer_age': np.random.normal(40, 10, 1000),
        'country_code': np.random.choice(['US', 'UK', 'DE', 'FR'], 1000),
        'device_type': np.random.choice(['mobile', 'desktop', 'tablet'], 1000),
    })

    detector = FeatureDriftDetector(
        reference_data=sample_ref_data,
        feature_columns=['transaction_amount', 'customer_age', 'country_code', 'device_type'],
        psi_threshold=0.2,
        ks_threshold=0.15,
        categorical_features=['country_code', 'device_type'],
    )

    current_data = pd.DataFrame({
        'transaction_amount': np.random.lognormal(5.2, 1.1, 100),
        'customer_age': np.random.normal(42, 12, 100),
        'country_code': np.random.choice(['US', 'UK', 'DE', 'FR'], 100),
        'device_type': np.random.choice(['mobile', 'desktop', 'tablet'], 100),
    })

    drift_results = detector.detect_all_drift(current_data)

    for result in drift_results:
        status = "VIOLATION" if result.is_violation else "OK"
        print(f"{result.feature_name}: {result.metric_name}={result.value:.4f} (threshold={result.threshold}) [{status}]")