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
]