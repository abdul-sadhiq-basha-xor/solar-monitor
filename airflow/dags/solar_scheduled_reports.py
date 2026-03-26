import os

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago


def _django_generate_reports(period: str):
    """
    Option A approach:
    Airflow schedules + triggers, Django generates CSV and writes DB record + file.
    """
    base_url = os.environ.get("DJANGO_BASE_URL", "http://host.docker.internal:8000").rstrip("/")
    token = os.environ.get("AIRFLOW_REPORTS_TOKEN", "")

    # Dev-friendly: you can later change this to "all owners" with a Django endpoint,
    # but for now keep it explicit. Start with owner_id=1 (first superuser typically).
    owner_id = int(os.environ.get("REPORT_OWNER_ID", "1"))

    url = f"{base_url}/api/airflow/reports/generate/"
    resp = requests.post(
        url,
        headers={"X-Airflow-Token": token},
        json={
            "owner_id": owner_id,
            "period": period,
            "plant_id": None,
            "airflow_dag_id": f"scheduled_{period.lower()}_reports",
            "airflow_run_id": os.environ.get("AIRFLOW_CTX_DAG_RUN_ID"),
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Django report generation failed: {data}")


default_args = {"owner": "airflow", "retries": 1}


with DAG(
    dag_id="scheduled_daily_reports",
    default_args=default_args,
    description="Generate daily CSV reports via Django API",
    schedule_interval="0 1 * * *",  # 01:00 daily
    start_date=days_ago(1),
    catchup=False,
    tags=["reports"],
) as dag_daily:
    PythonOperator(
        task_id="generate_daily_reports",
        python_callable=_django_generate_reports,
        op_kwargs={"period": "DAILY"},
    )


with DAG(
    dag_id="scheduled_weekly_reports",
    default_args=default_args,
    description="Generate weekly CSV reports via Django API",
    schedule_interval="0 2 * * 1",  # 02:00 every Monday
    start_date=days_ago(1),
    catchup=False,
    tags=["reports"],
) as dag_weekly:
    PythonOperator(
        task_id="generate_weekly_reports",
        python_callable=_django_generate_reports,
        op_kwargs={"period": "WEEKLY"},
    )


with DAG(
    dag_id="scheduled_monthly_reports",
    default_args=default_args,
    description="Generate monthly CSV reports via Django API",
    schedule_interval="0 3 1 * *",  # 03:00 on the 1st of every month
    start_date=days_ago(1),
    catchup=False,
    tags=["reports"],
) as dag_monthly:
    PythonOperator(
        task_id="generate_monthly_reports",
        python_callable=_django_generate_reports,
        op_kwargs={"period": "MONTHLY"},
    )

