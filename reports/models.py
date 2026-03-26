from pathlib import Path

from django.conf import settings
from django.db import models


class Report(models.Model):
    PERIOD_DAILY = "DAILY"
    PERIOD_WEEKLY = "WEEKLY"
    PERIOD_MONTHLY = "MONTHLY"
    PERIOD_CHOICES = [
        (PERIOD_DAILY, "Daily"),
        (PERIOD_WEEKLY, "Weekly"),
        (PERIOD_MONTHLY, "Monthly"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILURE = "FAILURE"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILURE, "Failure"),
    ]

    # Who the report is for (owners see their own; staff can see all)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports",
    )

    # Optional plant scoping (future: a single report can cover all plants)
    plant = models.ForeignKey(
        "plants.SolarPlant",
        on_delete=models.CASCADE,
        related_name="reports",
        null=True,
        blank=True,
    )

    period = models.CharField(max_length=20, choices=PERIOD_CHOICES)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=600)  # absolute path on host

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message = models.TextField(blank=True, null=True)

    # Airflow metadata (Option A)
    airflow_dag_id = models.CharField(max_length=255, blank=True, null=True)
    airflow_run_id = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        plant_part = f"plant={self.plant_id}" if self.plant_id else "all-plants"
        return f"{self.owner_id} {plant_part} {self.period} {self.status}"

    def file_exists(self) -> bool:
        try:
            return Path(self.file_path).exists()
        except Exception:
            return False

