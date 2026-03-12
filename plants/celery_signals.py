"""
Celery signal handlers — wired to every task in plants/tasks.py.

Tasks covered:
  readings_queue : simulate_solar_readings, demo_success, demo_failure,
                   demo_pending, demo_started, demo_retry
  long_tasks     : long_running_demo, process_csv_batch, fail_task
  long_tasks_dlq : handle_csv_dlq_message

Windows + pool=solo safe:
  - Uses a plain dict for start-time tracking (no multiprocessing).
  - Metrics server started via threading (see worker_metrics_server.start_metrics_server).
"""

import time
from typing import Dict

from celery.signals import (
    task_failure,
    task_postrun,
    task_prerun,
    task_retry,
    task_revoked,
    worker_ready,
)

from .metrics import (
    celery_tasks_in_progress,
    celery_tasks_total,
    celery_task_dlq_total,
    celery_task_retries_total,
    celery_task_runtime_seconds,
    csv_batch_size,
    csv_rows_failed_total,
    csv_rows_processed_total,
    demo_retry_attempts,
    solar_readings_created_total,
    solar_simulation_beat_lag_seconds,
    update_worker_metrics,
)
from .worker_metrics_server import start_metrics_server

# ── Queue map ──────────────────────────────────────────────────────────────────
# Maps task name → queue name so labels stay accurate even when
# Celery doesn't expose the queue in every signal callback.
TASK_QUEUE_MAP = {
    'plants.tasks.simulate_solar_readings': 'readings_queue',
    'plants.tasks.long_running_demo': 'long_tasks',
    'plants.tasks.process_csv_batch': 'long_tasks',
    'plants.tasks.handle_csv_dlq_message': 'long_tasks_dlq',
    'plants.tasks.fail_task': 'long_tasks',
    'plants.tasks.demo_success': 'readings_queue',
    'plants.tasks.demo_failure': 'readings_queue',
    'plants.tasks.demo_pending': 'readings_queue',
    'plants.tasks.demo_started': 'readings_queue',
    'plants.tasks.demo_retry': 'readings_queue',
}

# pool=solo → single process, plain dict is safe (no race conditions)
_task_start_times: Dict[str, float] = {}
_metrics_server_started: bool = False


def _queue_for(task_name: str) -> str:
    return TASK_QUEUE_MAP.get(task_name, 'unknown')


# ── Signal handlers ────────────────────────────────────────────────────────────

@task_prerun.connect
def on_task_prerun(task_id, task, *args, **kwargs):
    queue = _queue_for(task.name)
    _task_start_times[task_id] = time.monotonic()
    celery_tasks_in_progress.labels(queue=queue).inc()
    update_worker_metrics()


@task_postrun.connect
def on_task_postrun(task_id, task, retval, state, *args, **kwargs):
    task_name = task.name
    queue = _queue_for(task_name)
    start = _task_start_times.pop(task_id, None)

    # ── Runtime histogram ──────────────────────────────────────────
    if start is not None:
        duration = time.monotonic() - start
        celery_task_runtime_seconds.labels(
            task_name=task_name,
            queue=queue,
        ).observe(duration)

    # Decrement in-progress gauge
    celery_tasks_in_progress.labels(queue=queue).dec()

    # ── State counter ──────────────────────────────────────────────
    prometheus_state = 'success' if state == 'SUCCESS' else 'failure'
    celery_tasks_total.labels(
        task_name=task_name,
        queue=queue,
        state=prometheus_state,
    ).inc()

    # ── Task-specific metrics ──────────────────────────────────────

    # simulate_solar_readings — count readings + measure beat lag
    if task_name == 'plants.tasks.simulate_solar_readings' and state == 'SUCCESS':
        try:
            # Count the plants that were iterated
            from plants.models import SolarPlant

            plant_count = SolarPlant.objects.count()
            solar_readings_created_total.inc(plant_count)

            # Beat lag: compare beat_time arg to now
            beat_time_iso = kwargs.get('kwargs', {}).get('beat_time_iso')
            if beat_time_iso:
                from datetime import datetime

                from django.utils import timezone

                beat_time = datetime.fromisoformat(beat_time_iso)
                if beat_time.tzinfo is None:
                    beat_time = timezone.make_aware(beat_time)
                lag = (timezone.now() - beat_time).total_seconds()
                solar_simulation_beat_lag_seconds.observe(max(lag, 0))
        except Exception:
            # Metrics must never crash the task
            pass

    # process_csv_batch — record row counts from retval
    if task_name == 'plants.tasks.process_csv_batch' and state == 'SUCCESS':
        try:
            if isinstance(retval, dict) and retval.get('status') == 'SUCCESS':
                upload_id = str(kwargs.get('kwargs', {}).get('csv_upload_id', 'unknown'))
                successes = retval.get('successes', 0)
                errors = retval.get('errors', 0)
                total = retval.get('total', 0)

                csv_rows_processed_total.labels(upload_id=upload_id).inc(successes)
                csv_rows_failed_total.labels(upload_id=upload_id).inc(errors)

                if total > 0:
                    csv_batch_size.observe(total)
        except Exception:
            pass

    # demo_retry — record how many attempts it took
    if task_name == 'plants.tasks.demo_retry' and state == 'SUCCESS':
        try:
            attempt = retval.get('attempt', 1) if isinstance(retval, dict) else 1
            demo_retry_attempts.observe(attempt)
        except Exception:
            pass

    update_worker_metrics()


@task_failure.connect
def on_task_failure(task_id, exception, sender, *args, **kwargs):
    task_name = sender.name
    queue = _queue_for(task_name)

    celery_tasks_total.labels(
        task_name=task_name,
        queue=queue,
        state='failure',
    ).inc()

    # Decrement in-progress gauge if we have a start time tracked
    if _task_start_times.pop(task_id, None) is not None:
        celery_tasks_in_progress.labels(queue=queue).dec()

    # fail_task always rejects → DLQ
    if task_name == 'plants.tasks.fail_task':
        celery_task_dlq_total.labels(task_name=task_name).inc()

    update_worker_metrics()


@task_retry.connect
def on_task_retry(request, reason, *args, **kwargs):
    task_name = request.task
    queue = _queue_for(task_name)

    celery_task_retries_total.labels(task_name=task_name).inc()
    celery_tasks_total.labels(
        task_name=task_name,
        queue=queue,
        state='retry',
    ).inc()

    update_worker_metrics()


@task_revoked.connect
def on_task_revoked(request, *args, **kwargs):
    task_name = getattr(request, 'task', 'unknown')
    queue = _queue_for(task_name)

    celery_tasks_total.labels(
        task_name=task_name,
        queue=queue,
        state='rejected',
    ).inc()

    # Decrement in-progress gauge if we have a start time tracked
    task_id = getattr(request, 'id', None)
    if task_id and _task_start_times.pop(task_id, None) is not None:
        celery_tasks_in_progress.labels(queue=queue).dec()

    # process_csv_batch with simulate_dlq=True rejects on final attempt
    if task_name in ('plants.tasks.process_csv_batch', 'plants.tasks.fail_task'):
        celery_task_dlq_total.labels(task_name=task_name).inc()


@worker_ready.connect
def on_worker_ready(*args, **kwargs):
    """
    Called once when the worker boots — good place to take initial readings
    and start the dedicated Prometheus metrics HTTP server.
    """
    global _metrics_server_started

    update_worker_metrics()

    if not _metrics_server_started:
        # Start HTTP server on a background thread; failures are logged but
        # must not crash the worker.
        start_metrics_server()  # default port from WORKER_METRICS_PORT
        _metrics_server_started = True