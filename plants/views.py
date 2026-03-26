from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse
from celery.result import AsyncResult
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
import logging
import os
import tempfile
from .models import TaskResult


from .tasks import demo_success, demo_failure, demo_pending, demo_started, demo_retry
from .tasks import long_running_demo, process_csv_batch
from .pipeline_tasks import kickoff_demo_pipeline

logger = logging.getLogger(__name__)


def index(request):
    """Home page - shows signup/login for anon users, dashboard link for authenticated."""
    return render(request, 'plants/index.html')

from .models import SolarPlant, SolarReading, CSVUpload, FailedTask
from .services import SolarAnalyticsService
from .forms import SignUpForm, PlantForm, CSVImportForm


def signup(request):
    """Register a new user; a plant owner."""
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = SignUpForm()
    return render(request, 'plants/signup.html', {'form': form})


def logout_view(request):
    """Log out the user and redirect to signup page.
    Handles both GET and POST requests.
    """
    logout(request)
    return redirect('signup')


@login_required
def dashboard(request):
    """Dashboard showing plants and analytics."""
    # staff users can see all plants; owners only their own
    if request.user.is_staff:
        plants = SolarPlant.objects.all()
    else:
        plants = SolarPlant.objects.filter(owner=request.user)

    plant_data = []
    for plant in plants:
        plant_data.append({
            'plant': plant,
            'name': plant.name,
            'latest_power': SolarAnalyticsService.get_latest_power(plant),
            'today_energy': SolarAnalyticsService.get_today_energy(plant),
            'monthly_energy': SolarAnalyticsService.get_month_energy(plant),
            'battery': SolarAnalyticsService.get_latest_battery(plant),
        })

    return render(request, 'plants/dashboard.html', {'plants': plant_data})


@login_required
def plant_detail(request, pk):
    """Detail view for a single plant.

    Owners may only see their own plants; staff may view any plant.
    """
    if request.user.is_staff:
        plant = get_object_or_404(SolarPlant, pk=pk)
    else:
        plant = get_object_or_404(SolarPlant, pk=pk, owner=request.user)

    readings = plant.readings.all()[:100]
    context = {
        'plant': plant,
        'readings': readings,
        'latest_power': SolarAnalyticsService.get_latest_power(plant),
        'today_energy': SolarAnalyticsService.get_today_energy(plant),
        'monthly_energy': SolarAnalyticsService.get_month_energy(plant),
        'battery': SolarAnalyticsService.get_latest_battery(plant),
    }
    return render(request, 'plants/plant_detail.html', context)


@ensure_csrf_cookie
@login_required
def plant_create(request):
    """Create a new SolarPlant owned by the logged‑in user."""
    if request.method == 'POST':
        form = PlantForm(request.POST)
        if form.is_valid():
            plant = form.save(commit=False)
            plant.owner = request.user
            plant.save()
            return redirect('plant_detail', pk=plant.pk)
        else:
            # Log CSRF-related info for debugging when form submission fails
            try:
                posted = request.POST.get('csrfmiddlewaretoken')
                cookie = request.COOKIES.get('csrftoken')
                logger.warning('CSRF mismatch on plant_create POST - posted=%s cookie=%s', posted, cookie)
            except Exception:
                logger.exception('Error reading CSRF tokens during plant_create POST')
    else:
        form = PlantForm()
    return render(request, 'plants/plant_form.html', {'form': form})


@login_required
def plant_edit(request, pk):
    """Edit an existing plant (owner only)."""
    plant = get_object_or_404(SolarPlant, pk=pk, owner=request.user)
    if request.method == 'POST':
        form = PlantForm(request.POST, instance=plant)
        if form.is_valid():
            form.save()
            return redirect('plant_detail', pk=plant.pk)
    else:
        form = PlantForm(instance=plant)
    return render(request, 'plants/plant_form.html', {'form': form, 'plant': plant})


@login_required
def start_long_task(request):
    """Kick off the demo long-running Celery task and return task id.

    Use POST for safety; GET is not allowed. The template will send a POST
    with credentials so the session cookie is attached.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    task = long_running_demo.delay(duration=10)
    return JsonResponse({'task_id': task.id})


@login_required
def task_status(request):
    """Return JSON status for a given Celery task id (via GET param)."""
    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({'error': 'missing task_id'}, status=400)
    result = AsyncResult(task_id)
    try:
        status = result.status
        result_value = result.result
    except AttributeError:
        # backend doesn't support state retrieval
        return JsonResponse({'error': 'result backend not configured'}, status=500)

    response = {
        'status': status,
        'result': result_value,
    }
    if status == 'PROGRESS':
        response.update(result.info or {})
    return JsonResponse(response)


@login_required
def plant_import_csv(request, pk):
    """Upload and process CSV file for a plant's solar readings."""
    plant = get_object_or_404(SolarPlant, pk=pk, owner=request.user)
    
    if request.method == 'POST':
        form = CSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['file']
            
            # Save uploaded file to temp location
            temp_dir = tempfile.gettempdir()
            temp_file_path = os.path.join(temp_dir, f'solar_import_{plant.id}_{uploaded_file.name}')
            
            with open(temp_file_path, 'wb+') as f:
                for chunk in uploaded_file.chunks():
                    f.write(chunk)
            
            # Create CSVUpload record
            csv_upload = CSVUpload.objects.create(
                plant=plant,
                file_name=uploaded_file.name,
                file_path=temp_file_path,
                status='PENDING',
            )
            
            # Queue Celery task
            task = process_csv_batch.delay(csv_upload.id)
            csv_upload.task_id = task.id
            csv_upload.save()
            
            return JsonResponse({
                'success': True,
                'upload_id': csv_upload.id,
                'task_id': task.id,
            })
    else:
        form = CSVImportForm()
    
    return render(request, 'plants/csv_import.html', {
        'plant': plant,
        'form': form,
    })


@login_required
def import_progress(request, pk):
    """Check progress of CSV import for a plant."""
    upload_id = request.GET.get('upload_id')
    if not upload_id:
        return JsonResponse({'error': 'missing upload_id'}, status=400)
    
    try:
        upload = CSVUpload.objects.get(id=upload_id, plant__owner=request.user)
    except CSVUpload.DoesNotExist:
        return JsonResponse({'error': 'upload not found'}, status=404)
    
    # Check task status
    task_result = AsyncResult(upload.task_id)
    
    response = {
        'status': upload.status,
        'total_rows': upload.total_rows,
        'rows_processed': upload.rows_processed,
        'successes': upload.successes,
        'errors': upload.errors,
        'progress': upload.progress_percent(),
        'task_status': task_result.status,
    }
    
    if task_result.status == 'PROGRESS':
        response.update(task_result.info or {})
    
    return JsonResponse(response)


@login_required
def task_runner(request):
    """Task runner dashboard page."""
    return render(request, 'plants/task_runner.html')



@login_required
def trigger_task(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    task_type = request.POST.get('task_type')
    task_map = {
        'success': demo_success,
        'failure': demo_failure,
        'pending': demo_pending,
        'started': demo_started,
        'retry'  : demo_retry,
    }
    task_fn = task_map.get(task_type)
    if not task_fn:
        return JsonResponse({'error': 'Invalid task type'}, status=400)

    task = task_fn.delay()

    # ✅ Save to DB immediately as PENDING
    TaskResult.objects.create(
        task_id=task.id,
        task_type=task_type,
        status='PENDING'
    )

    return JsonResponse({'task_id': task.id, 'task_type': task_type})


@login_required
def fetch_task_result(request):
    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({'error': 'missing task_id'}, status=400)

    try:
        task = TaskResult.objects.get(task_id=task_id)
        return JsonResponse({
            'task_id': task.task_id,
            'task_type': task.task_type,
            'status': task.status,
            'result': task.result,
            'created_at': task.created_at.isoformat(),
            'updated_at': task.updated_at.isoformat(),
        })
    except TaskResult.DoesNotExist:
        return JsonResponse({'error': 'Task not found'}, status=404)


@login_required
def demo_pipeline_page(request):
    """
    Simple learning page to run a Celery chain (DAG-like 1->2->3).
    """
    from .models import DemoPipelineRun

    if request.user.is_staff:
        runs = DemoPipelineRun.objects.select_related("owner").all()[:50]
    else:
        runs = DemoPipelineRun.objects.select_related("owner").filter(owner=request.user)[:50]

    return render(request, "plants/demo_pipeline.html", {"runs": runs})


@login_required
def trigger_demo_pipeline(request):
    from .models import DemoPipelineRun

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    mode = (request.POST.get("mode") or DemoPipelineRun.MODE_SUCCESS).strip().lower()
    if mode not in {DemoPipelineRun.MODE_SUCCESS, DemoPipelineRun.MODE_RETRY, DemoPipelineRun.MODE_FAILURE}:
        return JsonResponse({"error": "invalid mode"}, status=400)

    run = DemoPipelineRun.objects.create(owner=request.user, mode=mode, status=DemoPipelineRun.STATUS_PENDING)
    async_result = kickoff_demo_pipeline(pipeline_id=run.id, mode=mode)
    DemoPipelineRun.objects.filter(id=run.id).update(celery_root_task_id=async_result.id)

    return JsonResponse({"ok": True, "pipeline_id": run.id, "root_task_id": async_result.id})


@login_required
def demo_pipeline_status(request, pipeline_id: int):
    from .models import DemoPipelineRun

    run = get_object_or_404(DemoPipelineRun, id=pipeline_id)
    if not request.user.is_staff and run.owner_id != request.user.id:
        return JsonResponse({"error": "not found"}, status=404)

    return JsonResponse(
        {
            "id": run.id,
            "mode": run.mode,
            "status": run.status,
            "current_step": run.current_step,
            "error_message": run.error_message,
            "root_task_id": run.celery_root_task_id,
            "created_at": run.created_at.isoformat(),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }
    )


def _airflow_token_ok(request) -> bool:
    from django.conf import settings

    expected = getattr(settings, "AIRFLOW_REPORTS_TOKEN", None)
    token = request.headers.get("X-Airflow-Token") or request.headers.get("x-airflow-token")
    return bool(expected and token and token == expected)


@csrf_exempt
@require_POST
def airflow_start_demo_pipeline(request):
    """
    Airflow -> Django: starts a Celery 1->2->3->4 demo pipeline and returns IDs.
    """
    if not _airflow_token_ok(request):
        return JsonResponse({"ok": False, "error": "unauthorized"}, status=401)

    import json
    from django.contrib.auth import get_user_model
    from .models import DemoPipelineRun

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    owner_id = int(payload.get("owner_id", 1))
    mode = (payload.get("mode") or DemoPipelineRun.MODE_SUCCESS).strip().lower()
    if mode not in {DemoPipelineRun.MODE_SUCCESS, DemoPipelineRun.MODE_RETRY, DemoPipelineRun.MODE_FAILURE}:
        return JsonResponse({"ok": False, "error": "invalid mode"}, status=400)

    User = get_user_model()
    owner = User.objects.get(id=owner_id)

    run = DemoPipelineRun.objects.create(owner=owner, mode=mode, status=DemoPipelineRun.STATUS_PENDING)
    async_result = kickoff_demo_pipeline(pipeline_id=run.id, mode=mode)
    DemoPipelineRun.objects.filter(id=run.id).update(celery_root_task_id=async_result.id)

    return JsonResponse({"ok": True, "pipeline_id": run.id, "root_task_id": async_result.id})


@csrf_exempt
@require_GET
def airflow_demo_pipeline_status(request, pipeline_id: int):
    """
    Airflow -> Django: polls pipeline status.
    """
    if not _airflow_token_ok(request):
        return JsonResponse({"ok": False, "error": "unauthorized"}, status=401)

    from .models import DemoPipelineRun

    run = get_object_or_404(DemoPipelineRun, id=pipeline_id)
    return JsonResponse(
        {
            "ok": True,
            "id": run.id,
            "mode": run.mode,
            "status": run.status,
            "current_step": run.current_step,
            "error_message": run.error_message,
            "root_task_id": run.celery_root_task_id,
            "created_at": run.created_at.isoformat(),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }
    )
