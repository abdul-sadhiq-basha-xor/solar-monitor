import os
from celery import Celery
from kombu import Queue, Exchange

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solar_monitor.settings')

app = Celery('solar_monitor')
app.config_from_object('django.conf:settings', namespace='CELERY')

# ── Exchanges ──────────────────────────────────────────────
readings_exchange = Exchange('readings_exchange', type='direct')
long_exchange     = Exchange('long_exchange',     type='direct')
long_dlx          = Exchange('long_tasks_dlx',    type='direct')

# ── Queues ─────────────────────────────────────────────────
readings_queue = Queue(
    'readings_queue',
    exchange=readings_exchange,
    routing_key='readings'
)

long_tasks_queue = Queue(
    'long_tasks',
    exchange=long_exchange,
    routing_key='long',
    queue_arguments={
        'x-dead-letter-exchange':    'long_tasks_dlx',
        'x-dead-letter-routing-key': 'long_tasks_dlq',
    }
)

long_tasks_dlq = Queue(
    'long_tasks_dlq',
    exchange=long_dlx,
    routing_key='long_tasks_dlq'
)

# ── Queues config ──────────────────────────────────────────
app.conf.task_queues = (
    readings_queue,
    long_tasks_queue,
    long_tasks_dlq,
)

# ── Routing ────────────────────────────────────────────────
app.conf.task_routes = {
    'plants.tasks.simulate_solar_readings':      {'queue': 'readings_queue', 'routing_key': 'readings'},
    'plants.tasks.process_csv_batch':            {'queue': 'long_tasks',     'routing_key': 'long'},
    'plants.tasks.long_running_demo':            {'queue': 'long_tasks',     'routing_key': 'long'},
    'plants.tasks.fail_task':                    {'queue': 'long_tasks',     'routing_key': 'long'},
    'plants.pipeline_tasks.pipeline_start':      {'queue': 'readings_queue', 'routing_key': 'readings'},
    'plants.pipeline_tasks.pipeline_work':       {'queue': 'long_tasks',     'routing_key': 'long'},
    'plants.pipeline_tasks.pipeline_postprocess':{'queue': 'readings_queue', 'routing_key': 'readings'},
    'plants.pipeline_tasks.pipeline_finalize':   {'queue': 'readings_queue', 'routing_key': 'readings'},
    'plants.pipeline_tasks.pipeline_mark_failed':{'queue': 'readings_queue', 'routing_key': 'readings'},
}

# ── Defaults ───────────────────────────────────────────────
app.conf.task_default_queue       = 'readings_queue'
app.conf.task_default_exchange    = 'readings_exchange'
app.conf.task_default_routing_key = 'readings'

# ── Autodiscover AFTER all config is set ───────────────────
app.autodiscover_tasks()

@app.on_after_configure.connect
def setup_signals(sender, **kwargs):
    import plants.celery_signals  # noqa: F401