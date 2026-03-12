import os

import psutil
from prometheus_client import Counter, Gauge, Histogram

# ─────────────────────────────────────────────
# CELERY TASK METRICS
# Tracks all tasks: simulate_solar_readings, long_running_demo,
# process_csv_batch, handle_csv_dlq_message, fail_task,
# demo_success, demo_failure, demo_pending, demo_started, demo_retry
# ─────────────────────────────────────────────

celery_tasks_total = Counter(
    'celery_tasks_total',
    'Total Celery tasks executed',
    ['task_name', 'queue', 'state'],  # state: success | failure | retry | rejected | dlq
)

celery_tasks_in_progress = Gauge(
    'celery_tasks_in_progress',
    'Number of Celery tasks currently running',
    ['queue'],
)

celery_task_runtime_seconds = Histogram(
    'celery_task_runtime_seconds',
    'Celery task execution duration in seconds',
    ['task_name', 'queue'],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float("inf")],
)

celery_task_retries_total = Counter(
    'celery_task_retries_total',
    'Total Celery task retries',
    ['task_name'],
)

celery_task_dlq_total = Counter(
    'celery_task_dlq_total',
    'Total tasks sent to Dead Letter Queue',
    ['task_name'],
)

# ─────────────────────────────────────────────
# CSV PROCESSING METRICS
# Specific to process_csv_batch task
# ─────────────────────────────────────────────

csv_rows_processed_total = Counter(
    'csv_rows_processed_total',
    'Total CSV rows successfully processed',
    ['upload_id'],
)

csv_rows_failed_total = Counter(
    'csv_rows_failed_total',
    'Total CSV rows that failed to process',
    ['upload_id'],
)

csv_batch_size = Histogram(
    'csv_batch_size',
    'Number of rows per CSV upload',
    buckets=[10, 50, 100, 250, 500, 1000, 5000, float("inf")],
)

# ─────────────────────────────────────────────
# SOLAR READINGS METRICS
# Specific to simulate_solar_readings task
# ─────────────────────────────────────────────

solar_readings_created_total = Counter(
    'solar_readings_created_total',
    'Total solar readings created by simulation task',
)

solar_simulation_beat_lag_seconds = Histogram(
    'solar_simulation_beat_lag_seconds',
    'Lag between beat scheduled time and worker processing time',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, float("inf")],
)

# ─────────────────────────────────────────────
# DEMO TASK METRICS
# Tracks demo_retry attempt distribution
# ─────────────────────────────────────────────

demo_retry_attempts = Histogram(
    'demo_retry_attempts',
    'Number of attempts before demo_retry task resolves',
    buckets=[1, 2, 3],
)

# ─────────────────────────────────────────────
# WORKER SYSTEM METRICS
# Memory + CPU for the single pool=solo worker process
# ─────────────────────────────────────────────

worker_memory_usage = Gauge(
    'worker_memory_usage',
    'Worker process RSS memory usage in bytes',
    ['worker_pid'],
)

worker_cpu_usage = Gauge(
    'worker_cpu_usage',
    'Worker process CPU usage percentage',
    ['worker_pid'],
)


def update_worker_metrics():
    """
    Update memory and CPU gauges for the current worker process.
    Safe for Windows + pool=solo (single process, no multiprocessing).
    """
    pid = str(os.getpid())
    try:
        process = psutil.Process(os.getpid())
        worker_memory_usage.labels(worker_pid=pid).set(process.memory_info().rss)
        worker_cpu_usage.labels(worker_pid=pid).set(process.cpu_percent(interval=0.1))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        # Metrics must never crash the worker
        pass