from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class SolarPlant(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=100)
    capacity_kw = models.FloatField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.capacity_kw} kW)"

class SolarReading(models.Model):
    plant = models.ForeignKey(
        SolarPlant,
        on_delete=models.CASCADE,
        related_name='readings'
    )

    timestamp = models.DateTimeField()
    beat_timestamp = models.DateTimeField(null=True, blank=True)  # ← ADD THIS

    power_kw = models.FloatField()
    battery_percentage = models.FloatField()
    grid_export_kw = models.FloatField()

    class Meta:
        ordering = ['-timestamp']
        constraints = [
            models.UniqueConstraint(
                fields=['plant', 'timestamp'],
                name='unique_plant_timestamp'
            )
        ]

    def __str__(self):
        return f"{self.plant.name} - {self.power_kw} kW"


class CSVUpload(models.Model):
    """Track CSV imports and their progress."""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    ]
    
    plant = models.ForeignKey(SolarPlant, on_delete=models.CASCADE, related_name='csv_uploads')
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    task_id = models.CharField(max_length=100, blank=True, null=True)  # Celery task ID
    rows_processed = models.IntegerField(default=0)
    total_rows = models.IntegerField(default=0)
    successes = models.IntegerField(default=0)
    errors = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        return f"CSV: {self.file_name} ({self.status})"
    
    def progress_percent(self):
        """Return progress as percentage."""
        if self.total_rows == 0:
            return 0
        return int((self.rows_processed / self.total_rows) * 100)


class FailedTask(models.Model):
    """Dead letter queue: tasks that failed after all retries."""
    task_name = models.CharField(max_length=255)
    task_id = models.CharField(max_length=100, unique=True)
    args = models.TextField()  # JSON serialized args
    error_message = models.TextField()
    retry_count = models.IntegerField(default=0)
    failed_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        return f"Failed: {self.task_name} ({self.task_id[:8]}...)"
    
    class Meta:
        ordering = ['-failed_at']