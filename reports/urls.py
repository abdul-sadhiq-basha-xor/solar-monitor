from django.urls import path

from . import views

urlpatterns = [
    path("reports/", views.reports_list, name="reports_list"),
    path("reports/generate/", views.report_generate_now, name="report_generate_now"),
    path("reports/<int:report_id>/download/", views.report_download, name="report_download"),
    # Option A: Airflow -> Django webhook
    path("api/airflow/reports/generate/", views.airflow_generate_report, name="airflow_generate_report"),
]

