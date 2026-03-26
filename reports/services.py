import csv
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.utils import timezone

from plants.models import SolarPlant, SolarReading


@dataclass(frozen=True)
class ReportWindow:
    start_at: datetime
    end_at: datetime


def _reports_output_dir() -> Path:
    base = getattr(settings, "REPORTS_OUTPUT_DIR", None)
    if base:
        return Path(base)
    return Path(settings.BASE_DIR) / "reports_output"


def compute_period_window(period: str, *, now: Optional[datetime] = None) -> ReportWindow:
    """
    Daily: previous local day [00:00, 00:00)
    Weekly: previous local week Mon..Mon
    Monthly: previous local month 1st..1st
    """
    if now is None:
        now = timezone.localtime(timezone.now())
    else:
        now = timezone.localtime(now)

    if period == "DAILY":
        today = now.date()
        start_date = today - timedelta(days=1)
        start_at = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_at = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        return ReportWindow(start_at=start_at, end_at=end_at)

    if period == "WEEKLY":
        # Monday is 0
        this_monday = (now - timedelta(days=now.weekday())).date()
        prev_monday = this_monday - timedelta(days=7)
        start_at = timezone.make_aware(datetime.combine(prev_monday, datetime.min.time()))
        end_at = timezone.make_aware(datetime.combine(this_monday, datetime.min.time()))
        return ReportWindow(start_at=start_at, end_at=end_at)

    if period == "MONTHLY":
        first_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_end = first_this_month - timedelta(seconds=1)
        first_last_month = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return ReportWindow(start_at=first_last_month, end_at=first_this_month)

    raise ValueError(f"Unknown period: {period}")


def generate_csv_report_for_owner(
    *,
    owner_id: int,
    period: str,
    plant_id: Optional[int],
    airflow_dag_id: Optional[str] = None,
    airflow_run_id: Optional[str] = None,
) -> "reports.models.Report":
    """
    Generates a CSV report on disk and creates a Report DB record.
    """
    from reports.models import Report
    from django.contrib.auth import get_user_model

    window = compute_period_window(period)
    User = get_user_model()
    owner = User.objects.get(id=owner_id)

    plant = None
    if plant_id is not None:
        plant = SolarPlant.objects.get(id=plant_id)

    output_dir = _reports_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_period = period.lower()
    ts = timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M%S")
    plant_part = f"plant_{plant_id}" if plant_id else "all_plants"
    file_name = f"report_{safe_period}_{plant_part}_owner_{owner_id}_{ts}.csv"
    file_path = str(output_dir / file_name)

    report = Report.objects.create(
        owner=owner,
        plant=plant,
        period=period,
        start_at=window.start_at,
        end_at=window.end_at,
        file_name=file_name,
        file_path=file_path,
        status=Report.STATUS_PENDING,
        airflow_dag_id=airflow_dag_id,
        airflow_run_id=airflow_run_id,
    )

    try:
        # Decide which plants are included
        if plant is not None:
            plants_qs = SolarPlant.objects.filter(id=plant.id)
        else:
            plants_qs = SolarPlant.objects.filter(owner=owner)

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "report_id",
                    "owner_id",
                    "plant_id",
                    "plant_name",
                    "period",
                    "start_at",
                    "end_at",
                    "reading_timestamp",
                    "power_kw",
                    "battery_percentage",
                    "grid_export_kw",
                ]
            )

            for p in plants_qs.iterator():
                readings = (
                    SolarReading.objects.filter(plant=p, timestamp__gte=window.start_at, timestamp__lt=window.end_at)
                    .order_by("timestamp")
                    .iterator()
                )
                for r in readings:
                    writer.writerow(
                        [
                            report.id,
                            owner_id,
                            p.id,
                            p.name,
                            period,
                            window.start_at.isoformat(),
                            window.end_at.isoformat(),
                            timezone.localtime(r.timestamp).isoformat(),
                            r.power_kw,
                            r.battery_percentage,
                            r.grid_export_kw,
                        ]
                    )

        report.status = Report.STATUS_SUCCESS
        report.save(update_fields=["status"])
        return report

    except Exception as exc:
        # best-effort cleanup
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
        report.status = Report.STATUS_FAILURE
        report.error_message = str(exc)
        report.save(update_fields=["status", "error_message"])
        raise

