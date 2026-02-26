import random
from datetime import datetime
from celery import shared_task
from django.utils import timezone
from .models import SolarPlant, SolarReading


@shared_task
def simulate_solar_readings():
    plants = SolarPlant.objects.all()

    for plant in plants:
        #current_hour = timezone.now().hour
        current_hour = timezone.localtime(timezone.now()).hour  # ✅ use localtime


        # Daytime simulation (6 AM to 6 PM)
        if 6 <= current_hour <= 18:
            # Generate production based on capacity
            power_output = random.uniform(
                plant.capacity_kw * 0.3,
                plant.capacity_kw * 1.0
            )
        else:
            power_output = 0.0  # No production at night

        battery_percentage = random.uniform(20, 100)
        grid_export = max(0, power_output - (plant.capacity_kw * 0.5))

        SolarReading.objects.create(
            plant=plant,
            power_kw=round(power_output, 2),
            battery_percentage=round(battery_percentage, 2),
            grid_export_kw=round(grid_export, 2)
        )

    return "Simulation completed"