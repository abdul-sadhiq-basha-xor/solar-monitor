from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "plant", "period", "status", "created_at")
    list_filter = ("period", "status", "created_at")
    search_fields = ("owner__username", "file_name", "airflow_dag_id", "airflow_run_id")

