import random
from celery import shared_task
from celery import current_task
from celery.exceptions import Reject
from django.utils import timezone
from .models import SolarPlant, SolarReading, CSVUpload, FailedTask
import csv
import json
from django.db import transaction
import time  # ← make sure this is at the top
from datetime import datetime  # ← datetime separately
import random


@shared_task(bind=True, queue='readings_queue')
def simulate_solar_readings(self, beat_time_iso: str = None):
    # Beat time injected by TimeInjectingScheduler
    if beat_time_iso:
        beat_time = datetime.fromisoformat(beat_time_iso)
        if beat_time.tzinfo is None:
            beat_time = timezone.make_aware(beat_time)
    else:
        beat_time = timezone.now()

    worker_time = timezone.now()  # actual time worker processed

    plants = SolarPlant.objects.all()
    for plant in plants:
        current_hour = timezone.localtime(beat_time).hour
        power_output = (
            random.uniform(plant.capacity_kw * 0.3, plant.capacity_kw * 1.0)
            if 6 <= current_hour <= 25 else 0.0
        )
        battery_percentage = random.uniform(20, 100)
        grid_export = max(0, power_output - (plant.capacity_kw * 0.5))

        SolarReading.objects.create(
            plant=plant,
            timestamp=worker_time,          # when worker processed
            beat_timestamp=beat_time,        # ✅ exact Beat schedule time
            power_kw=round(power_output, 2),
            battery_percentage=round(battery_percentage, 2),
            grid_export_kw=round(grid_export, 2)
        )

    return f"Simulation completed for beat={beat_time.isoformat()}"


def k8s_simulate_solar_readings():
    """
    Standalone function for Kubernetes pod execution.
    No Celery dependency — called directly by KubernetesPodOperator.
    Uses timezone.now() as the execution time.
    """
    from plants.models import SolarPlant, SolarReading
    from django.utils import timezone
    import random

    beat_time = timezone.now()

    plants = SolarPlant.objects.all()
    count = 0
    for plant in plants:
        current_hour = timezone.localtime(beat_time).hour
        power_output = (
            random.uniform(plant.capacity_kw * 0.3, plant.capacity_kw * 1.0)
            if 6 <= current_hour <= 18 else 0.0
        )
        battery_percentage = random.uniform(20, 100)
        grid_export = max(0, power_output - (plant.capacity_kw * 0.5))

        SolarReading.objects.create(
            plant=plant,
            timestamp=beat_time,
            beat_timestamp=beat_time,
            power_kw=round(power_output, 2),
            battery_percentage=round(battery_percentage, 2),
            grid_export_kw=round(grid_export, 2),
        )
        count += 1

    print(f"[K8s] Simulation completed — {count} readings written at {beat_time.isoformat()}")
    return count


@shared_task(bind=True,queue='long_tasks')
def long_running_demo(self, duration=10):
    """Simulate a long task by sleeping, reporting progress.

    `duration` is number of seconds; the task updates its state every second.
    """
    total = int(duration)
    for i in range(total):
        # simulate work
        import time
        time.sleep(1)
        self.update_state(state='PROGRESS', meta={'current': i + 1, 'total': total})
    return {'current': total, 'total': total, 'status': 'Completed'}


@shared_task(
    bind=True,
    queue='long_tasks',
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3},
    default_retry_delay=5  # Wait 5 seconds between retries
)
def process_csv_batch(self, csv_upload_id, simulate_dlq=False):
    """
    Import solar readings from CSV in chunks with automatic retry mechanism.

    Args:
        csv_upload_id: ID of the CSVUpload record to process
        simulate_dlq: If True, task will fail intentionally to test DLQ handling

    Retry Behavior:
    - Automatically retries up to 3 times on any Exception
    - After 3 failed attempts, the task is sent to the Dead Letter Queue (DLQ)
    - This is useful for handling temporary failures (network issues, DB locks, etc.)

    DLQ Handling:
    - Failed tasks end up in 'long_tasks_dlq' queue for manual review/processing
    - Check the FailedTask model for logging failed CSV imports
    """
    try:
        upload = CSVUpload.objects.get(id=csv_upload_id)
        upload.status = 'PROCESSING'
        upload.save()

        # Simulate failure for testing DLQ (comment out or set simulate_dlq=False for production)
        if simulate_dlq:
            current_attempt = self.request.retries + 1
            max_attempts = 4  # 1 initial + 3 retries
            print(f"[DLQ Test] Attempt {current_attempt}/{max_attempts} - raising intentional failure")
            if current_attempt < max_attempts:
                # This will trigger retry mechanism
                raise Exception(f"Intentional DLQ test failure - attempt {current_attempt}/{max_attempts}")
            else:
                # Final attempt: explicitly reject the underlying AMQP message so RabbitMQ
                # routes it to the Dead Letter Exchange/Queue (DLQ).
                try:
                    msg = getattr(self.request, 'message', None)
                    if msg is not None:
                        # reject without requeue => goes to DLQ (per queue arguments)
                        msg.reject(requeue=False)
                        print("[DLQ] Underlying message rejected to DLQ")
                    else:
                        print("[DLQ] No underlying message object available to reject")
                except Exception as _e:
                    print(f"[DLQ] Failed to reject message directly: {_e}")
                # raise to mark task failed (no further retries expected)
                raise Exception(f"Intentional DLQ final failure - attempt {current_attempt}/{max_attempts}")

        # -----------------------------
        # Normal CSV processing
        # -----------------------------
        with open(upload.file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        upload.total_rows = len(rows)
        upload.save()

        if not rows:
            upload.status = 'SUCCESS'
            upload.completed_at = timezone.now()
            upload.save()
            return {'status': 'SUCCESS', 'msg': 'Empty CSV'}

        # -----------------------------
        # Process CSV in small chunks
        # -----------------------------
        chunk_size = 5  # smaller chunks for demonstration
        successes = 0
        errors = 0

        for chunk_idx in range(0, len(rows), chunk_size):
            chunk = rows[chunk_idx:chunk_idx + chunk_size]

            for row in chunk:
                try:
                    SolarReading.objects.create(
                        plant=upload.plant,
                        timestamp=datetime.fromisoformat(row['timestamp']),
                        power_kw=float(row['power_kw']),
                        battery_percentage=float(row['battery_percentage']),
                        grid_export_kw=float(row.get('grid_export_kw', 0))
                    )
                    successes += 1
                except (ValueError, KeyError):
                    errors += 1
                    continue

            upload.rows_processed = min(chunk_idx + chunk_size, len(rows))
            upload.successes = successes
            upload.errors = errors
            upload.save()

        # -----------------------------
        # SUCCESS
        # -----------------------------
        upload.status = 'SUCCESS'
        upload.completed_at = timezone.now()
        upload.save()

        return {
            'status': 'SUCCESS',
            'total': upload.total_rows,
            'successes': successes,
            'errors': errors
        }

    except CSVUpload.DoesNotExist as exc:
        error_msg = f"CSVUpload record (ID: {csv_upload_id}) not found"
        print(f"[ERROR] {error_msg}")
        FailedTask.objects.create(
            task_name='process_csv_batch',
            task_id=self.request.id,
            args=json.dumps({'csv_upload_id': csv_upload_id}),
            error_message=error_msg,
            retry_count=self.request.retries
        )
        raise

    except Exception as exc:
        current_attempt = self.request.retries + 1
        print(f"[RETRY {current_attempt}/3] Task failed: {exc}")
        
        # Log to FailedTask model
        FailedTask.objects.update_or_create(
            task_id=self.request.id,
            defaults={
                'task_name': 'process_csv_batch',
                'args': json.dumps({'csv_upload_id': csv_upload_id}),
                'error_message': str(exc),
                'retry_count': current_attempt
            }
        )
        
        # Mark upload as FAILED if this was the last retry attempt
        if current_attempt >= 3:
            try:
                upload = CSVUpload.objects.get(id=csv_upload_id)
                upload.status = 'FAILED'
                upload.completed_at = timezone.now()
                upload.save()
                print(f"[DLQ] Task moved to Dead Letter Queue after {current_attempt} attempts")
            except CSVUpload.DoesNotExist:
                pass
        
        # Re-raise to trigger retry or move to DLQ
        raise self.retry(exc=exc)


@shared_task(queue='long_tasks_dlq')
def handle_csv_dlq_message(task_id, csv_upload_id, error_message):
    """
    Handler for messages in the CSV processing Dead Letter Queue.
    
    This task is triggered when a message is moved to DLQ after all retries are exhausted.
    It provides a way to log, monitor, and potentially retry or escalate the failed task.
    
    Args:
        task_id: Original Celery task ID
        csv_upload_id: ID of the CSVUpload record
        error_message: Error message from the original task failure
    """
    print(f"[DLQ HANDLER] Processing failed task: {task_id}")
    print(f"[DLQ HANDLER] CSV Upload ID: {csv_upload_id}")
    print(f"[DLQ HANDLER] Error: {error_message}")
    
    try:
        # Record the failure
        failed_task = FailedTask.objects.get(task_id=task_id)
        failed_task.resolved = False
        failed_task.save()
        
        # Update the upload status
        upload = CSVUpload.objects.get(id=csv_upload_id)
        upload.status = 'FAILED'
        upload.error_message = f"Task failed after all retries. Error: {error_message}"
        upload.completed_at = timezone.now()
        upload.save()
        
        return {
            'status': 'DLQ_PROCESSED',
            'task_id': task_id,
            'csv_upload_id': csv_upload_id,
            'logged': True
        }
    except (FailedTask.DoesNotExist, CSVUpload.DoesNotExist) as exc:
        print(f"[DLQ HANDLER] Error processing DLQ message: {exc}")
        return {
            'status': 'DLQ_ERROR',
            'error': str(exc)
        }

@shared_task(bind=True, queue="long_tasks", acks_late=True)
def fail_task(self, data):
    print(f"Processing: {data}")
    delivery_info = self.request.delivery_info
    raise Reject("Task rejected to DLQ", requeue=False)

@shared_task(bind=True, queue='readings_queue')
def demo_success(self):
    from .models import TaskResult
    TaskResult.objects.filter(task_id=self.request.id).update(status='STARTED')
    time.sleep(2)
    TaskResult.objects.filter(task_id=self.request.id).update(
        status='SUCCESS',
        result='Task completed successfully!'
    )
    return {'status': 'success', 'message': 'Task completed successfully!'}


@shared_task(bind=True, queue='readings_queue')
def demo_failure(self):
    from .models import TaskResult
    TaskResult.objects.filter(task_id=self.request.id).update(status='STARTED')
    time.sleep(2)
    TaskResult.objects.filter(task_id=self.request.id).update(
        status='FAILURE',
        result='Intentional failure for demo purposes'
    )
    raise Exception('Intentional failure for demo purposes')


@shared_task(bind=True, queue='readings_queue')
def demo_pending(self):
    from .models import TaskResult
    time.sleep(30)
    TaskResult.objects.filter(task_id=self.request.id).update(
        status='SUCCESS',
        result='Pending task done'
    )
    return {'status': 'done'}


@shared_task(bind=True, queue='readings_queue')
def demo_started(self):
    from .models import TaskResult
    TaskResult.objects.filter(task_id=self.request.id).update(status='STARTED')
    time.sleep(10)
    TaskResult.objects.filter(task_id=self.request.id).update(
        status='SUCCESS',
        result='Started task completed'
    )
    return {'status': 'success', 'message': 'Started task done'}


@shared_task(bind=True, queue='readings_queue', max_retries=3)
def demo_retry(self):
    from .models import TaskResult
    
    current_attempt = self.request.retries + 1  # 1, 2, 3
    total_attempts = 3

    # Update DB to show which attempt we're on
    TaskResult.objects.filter(task_id=self.request.id).update(
        status='STARTED',
        result=f'Attempt {current_attempt}/{total_attempts}...'
    )

    time.sleep(2)  # simulate work

    # Randomly decide success or failure (50/50)
    will_succeed = random.choice([True, False])

    if will_succeed:
        # 🎉 Success!
        TaskResult.objects.filter(task_id=self.request.id).update(
            status='SUCCESS',
            result=f'Succeeded on attempt {current_attempt}/{total_attempts}!'
        )
        return {'status': 'success', 'attempt': current_attempt}

    else:
        # ❌ Failed this attempt
        if current_attempt < total_attempts:
            # Still have retries left → retry after 3 seconds
            TaskResult.objects.filter(task_id=self.request.id).update(
                status='STARTED',
                result=f'Attempt {current_attempt} failed. Retrying in 3s... ({current_attempt}/{total_attempts})'
            )
            raise self.retry(countdown=3)  # retry after 3 seconds

        else:
            # All retries exhausted → final failure
            TaskResult.objects.filter(task_id=self.request.id).update(
                status='FAILURE',
                result=f'Failed after {total_attempts} attempts.'
            )
            raise Exception(f'Failed after {total_attempts} attempts.')