import os
from celery import Celery
from kombu import Queue, Exchange

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar_monitor.settings')

app = Celery('solar_monitor')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# -----------------------------
# Exchanges
# -----------------------------
readings_exchange = Exchange('readings_exchange', type='direct')
long_exchange = Exchange('long_exchange', type='direct')
long_dlx = Exchange('long_tasks_dlx', type='direct')  # Dead Letter Exchange

# -----------------------------
# Queues
# -----------------------------
readings_queue = Queue('readings_queue', exchange=readings_exchange, routing_key='readings')

long_tasks_queue = Queue(
    'long_tasks',
    exchange=long_exchange,
    routing_key='long',
    queue_arguments={
        'x-dead-letter-exchange': 'long_tasks_dlx',        # DLX
        'x-dead-letter-routing-key': 'long_tasks_dlq'      # DLQ routing key
    }
)

long_tasks_dlq = Queue(
    'long_tasks_dlq',
    exchange=long_dlx,
    routing_key='long_tasks_dlq'
)

# -----------------------------
# Celery task queues
# -----------------------------
app.conf.task_queues = (
    readings_queue,
    long_tasks_queue,
    long_tasks_dlq,
)

# -----------------------------
# Task routing
# -----------------------------
app.conf.task_routes = {
    'plants.tasks.simulate_solar_readings': {'queue': 'readings_queue', 'routing_key': 'readings'},
    'plants.tasks.process_csv_batch': {'queue': 'long_tasks', 'routing_key': 'long'},
    'plants.tasks.long_running_demo': {'queue': 'long_tasks', 'routing_key': 'long'},
    'plants.tasks.fail_task': {'queue': 'long_tasks', 'routing_key': 'long'},
}