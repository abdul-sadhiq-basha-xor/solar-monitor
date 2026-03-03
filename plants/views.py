from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse
from celery.result import AsyncResult
from django.views.decorators.csrf import ensure_csrf_cookie
import logging
import os
import tempfile

from .tasks import long_running_demo, process_csv_batch

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
