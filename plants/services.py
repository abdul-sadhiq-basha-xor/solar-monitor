from django.utils import timezone
from django.db.models import Sum
from .models import SolarPlant, SolarReading


class SolarAnalyticsService:

    @staticmethod
    def get_latest_power(plant):
        latest = plant.readings.first()
        return latest.power_kw if latest else 0

    @staticmethod
    def get_today_energy(plant):
        today = timezone.now().date()
        readings = plant.readings.filter(timestamp__date=today)

        total_power = readings.aggregate(Sum('power_kw'))['power_kw__sum'] or 0

        # Convert kW readings to kWh (1 reading per minute)
        return round(total_power / 60, 2)

    @staticmethod
    def get_month_energy(plant):
        now = timezone.now()
        readings = plant.readings.filter(
            timestamp__year=now.year,
            timestamp__month=now.month
        )

        total_power = readings.aggregate(Sum('power_kw'))['power_kw__sum'] or 0

        return round(total_power / 60, 2)

    @staticmethod
    def get_total_energy(plant):
        total_power = plant.readings.aggregate(Sum('power_kw'))['power_kw__sum'] or 0
        return round(total_power / 60, 2)
    
    @staticmethod
    def get_latest_battery(plant):
        """Return the latest battery % for a given plant"""
        latest = SolarReading.objects.filter(plant=plant).order_by('-timestamp').first()
        return latest.battery_percentage if latest else 0