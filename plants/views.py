from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect


def index(request):
    """Home page - shows signup/login for anon users, dashboard link for authenticated."""
    return render(request, 'plants/index.html')

from .models import SolarPlant
from .services import SolarAnalyticsService
from .forms import SignUpForm, PlantForm


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