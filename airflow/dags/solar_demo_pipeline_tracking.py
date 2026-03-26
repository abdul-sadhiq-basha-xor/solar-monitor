import os
import time

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago


def _start_pipeline(**context):
    base_url = os.environ.get("DJANGO_BASE_URL", "http://host.docker.internal:8000").rstrip("/")
    token = os.environ.get("AIRFLOW_REPORTS_TOKEN", "")

    owner_id = int(os.environ.get("PIPELINE_OWNER_ID", "1"))
    mode = os.environ.get("PIPELINE_MODE", "success")

    resp = requests.post(
        f"{base_url}/api/airflow/pipelines/demo/start/",
        headers={"X-Airflow-Token": token},
        json={"owner_id": owner_id, "mode": mode},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Failed to start pipeline: {data}")

    context["ti"].xcom_push(key="pipeline_id", value=data["pipeline_id"])
    context["ti"].xcom_push(key="root_task_id", value=data.get("root_task_id"))


def _wait_for_pipeline(**context):
    base_url = os.environ.get("DJANGO_BASE_URL", "http://host.docker.internal:8000").rstrip("/")
    token = os.environ.get("AIRFLOW_REPORTS_TOKEN", "")

    pipeline_id = context["ti"].xcom_pull(key="pipeline_id", task_ids="start_demo_pipeline")
    if not pipeline_id:
        raise RuntimeError("Missing pipeline_id from XCom")

    timeout_s = int(os.environ.get("PIPELINE_POLL_TIMEOUT_S", "120"))
    interval_s = int(os.environ.get("PIPELINE_POLL_INTERVAL_S", "2"))

    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        resp = requests.get(
            f"{base_url}/api/airflow/pipelines/demo/{pipeline_id}/status/",
            headers={"X-Airflow-Token": token},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        last = data

        status = data.get("status")
        if status == "SUCCESS":
            return
        if status == "FAILURE":
            raise RuntimeError(f"Pipeline failed: {data.get('error_message')}")

        time.sleep(interval_s)

    raise RuntimeError(f"Pipeline polling timed out. Last status: {last}")


default_args = {"owner": "airflow", "retries": 0}


with DAG(
    dag_id="track_celery_demo_pipeline",
    default_args=default_args,
    description="Trigger a Celery 1->2->3->4 chain and track via Django status API",
    schedule_interval=None,  # manual trigger for learning
    start_date=days_ago(1),
    catchup=False,
    tags=["celery", "pipelines", "learning"],
) as dag:
    start = PythonOperator(task_id="start_demo_pipeline", python_callable=_start_pipeline, provide_context=True)
    wait = PythonOperator(task_id="wait_for_completion", python_callable=_wait_for_pipeline, provide_context=True)

    start >> wait

