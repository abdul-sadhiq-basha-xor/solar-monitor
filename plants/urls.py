from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('signup/', views.signup, name='signup'),
    path('plants/add/', views.plant_create, name='plant_create'),
    path('plants/<int:pk>/', views.plant_detail, name='plant_detail'),
    path('plants/<int:pk>/edit/', views.plant_edit, name='plant_edit'),
    # CSV import endpoints
    path('plants/<int:pk>/import/', views.plant_import_csv, name='plant_import_csv'),
    path('plants/<int:pk>/import-progress/', views.import_progress, name='import_progress'),
    # demo celery endpoints
    path('tasks/long/', views.start_long_task, name='start_long_task'),
    path('tasks/status/', views.task_status, name='task_status'),

    path('tasks/runner/', views.task_runner, name='task_runner'),
    path('tasks/trigger/', views.trigger_task, name='trigger_task'),
    path('tasks/result/', views.fetch_task_result, name='fetch_task_result'),

    # Celery DAG-style demo pipeline
    path('pipelines/demo/', views.demo_pipeline_page, name='demo_pipeline_page'),
    path('pipelines/demo/trigger/', views.trigger_demo_pipeline, name='trigger_demo_pipeline'),
    path('pipelines/demo/<int:pipeline_id>/status/', views.demo_pipeline_status, name='demo_pipeline_status'),

    # Airflow token-protected endpoints (Option A tracking)
    path('api/airflow/pipelines/demo/start/', views.airflow_start_demo_pipeline, name='airflow_start_demo_pipeline'),
    path('api/airflow/pipelines/demo/<int:pipeline_id>/status/', views.airflow_demo_pipeline_status, name='airflow_demo_pipeline_status'),
]