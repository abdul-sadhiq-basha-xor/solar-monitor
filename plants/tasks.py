import random
from datetime import datetime
from celery import shared_task
from celery import current_task
from django.utils import timezone
from .models import SolarPlant, SolarReading, CSVUpload, FailedTask
import csv
import json
from django.db import transaction


@shared_task
def simulate_solar_readings():
    plants = SolarPlant.objects.all()

    for plant in plants:
        #current_hour = timezone.now().hour
        current_hour = timezone.localtime(timezone.now()).hour  # ✅ use localtime


        # Daytime simulation (6 AM to 6 PM)
        if 6 <= current_hour <= 18:
            # Generate production based on capacity
            power_output = random.uniform(
                plant.capacity_kw * 0.3,
                plant.capacity_kw * 1.0
            )
        else:
            power_output = 0.0  # No production at night

        battery_percentage = random.uniform(20, 100)
        grid_export = max(0, power_output - (plant.capacity_kw * 0.5))

        SolarReading.objects.create(
            plant=plant,
            power_kw=round(power_output, 2),
            battery_percentage=round(battery_percentage, 2),
            grid_export_kw=round(grid_export, 2)
        )

    return "Simulation completed"


@shared_task(bind=True)
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


@shared_task(bind=True, max_retries=3)
def process_csv_batch(self, csv_upload_id):
    """
    Import solar readings from CSV file in chunks.
    
    Args:
        csv_upload_id: ID of CSVUpload model instance
    
    Chunks are 100 rows at a time. Task retries up to 3 times on failure
    with exponential backoff (2, 4, 8 seconds).
    """
    try:
        upload = CSVUpload.objects.get(id=csv_upload_id)
        upload.status = 'PROCESSING'
        upload.save()
        
        # Read CSV file
        with open(upload.file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        if not rows:
            upload.status = 'SUCCESS'
            upload.total_rows = 0
            upload.completed_at = timezone.now()
            upload.save()
            return {'status': 'SUCCESS', 'msg': 'Empty CSV'}
        
        upload.total_rows = len(rows)
        upload.save()
        
        # Process in chunks of 100
        chunk_size = 100
        successes = 0
        errors = 0
        
        for chunk_idx in range(0, len(rows), chunk_size):
            chunk = rows[chunk_idx:chunk_idx + chunk_size]
            created_count = 0
            
            # Use transaction to rollback entire chunk if any error
            try:
                with transaction.atomic():
                    for row in chunk:
                        try:
                            # Expect: timestamp, power_kw, battery_percentage, grid_export_kw
                            reading = SolarReading(
                                plant=upload.plant,
                                timestamp=datetime.fromisoformat(row['timestamp']),
                                power_kw=float(row['power_kw']),
                                battery_percentage=float(row['battery_percentage']),
                                grid_export_kw=float(row.get('grid_export_kw', 0))
                            )
                            reading.save()
                            created_count += 1
                            successes += 1
                        except (ValueError, KeyError) as e:
                            errors += 1
                            # Skip invalid row, continue processing
                            continue
            except Exception as e:
                # Chunk processing failed
                errors += len(chunk) - created_count
            
            # Update progress
            upload.rows_processed = chunk_idx + chunk_size
            upload.successes = successes
            upload.errors = errors
            upload.save()
            
            # Report to Celery progress tracking
            self.update_state(state='PROGRESS', meta={
                'current': upload.rows_processed,
                'total': upload.total_rows,
                'successes': successes,
                'errors': errors,
            })
        
        # Success!
        upload.status = 'SUCCESS'
        upload.completed_at = timezone.now()
        upload.save()
        
        return {
            'status': 'SUCCESS',
            'total': upload.total_rows,
            'successes': successes,
            'errors': errors
        }
    
    except CSVUpload.DoesNotExist:
        return {'error': 'CSVUpload record not found'}
    
    except Exception as exc:
        # Retry with exponential backoff: 2^retry_count seconds
        retry_delay = 2 ** self.request.retries
        try:
            self.retry(exc=exc, countdown=retry_delay)
        except self.MaxRetriesExceededError:
            # All retries exhausted - save to dead letter queue
            upload.status = 'FAILED'
            upload.error_message = str(exc)
            upload.completed_at = timezone.now()
            upload.save()
            
            # Save to FailedTask for admin review
            FailedTask.objects.create(
                task_name='process_csv_batch',
                task_id=self.request.id,
                args=json.dumps({'csv_upload_id': csv_upload_id}),
                error_message=str(exc),
                retry_count=self.request.retries,
            )
            
            return {'error': f'Task failed after {self.request.retries} retries: {str(exc)}'}
