from datetime import datetime
from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

with DAG(
    dag_id="k8s_simulate_solar_readings",
    description="Run k8s_simulate_solar_readings in a Kubernetes pod every minute",
    schedule_interval="* * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["k8s", "readings"],
) as dag:

    simulate_readings = KubernetesPodOperator(
    task_id="simulate_solar_readings",
    name="simulate-solar-readings",
    namespace="airflow",
    image="solar-monitor-airflow:latest",
    image_pull_policy="Never",
    service_account_name="airflow-sa",  # use the SA you created
    cmds=["python"],
    arguments=[
        "-c",
        """
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar_monitor.settings')
django.setup()
from plants.tasks import k8s_simulate_solar_readings
count = k8s_simulate_solar_readings()
print(f'[K8s] Done — {count} readings written')
        """
    ],
    env_vars=[
        k8s.V1EnvVar(name="DJANGO_SETTINGS_MODULE", value="solar_monitor.settings"),
        k8s.V1EnvVar(name="PYTHONPATH", value="/opt/airflow/solar_monitor"),
    ],
    container_resources=k8s.V1ResourceRequirements(
        requests={"cpu": "100m", "memory": "256Mi"},
        limits={"cpu": "500m", "memory": "512Mi"},
    ),
    is_delete_operator_pod=False,  # keep pod after failure for debugging
    get_logs=True,
    do_xcom_push=False,
)