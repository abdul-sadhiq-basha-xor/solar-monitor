from django.db import models
from django.contrib.auth.models import User


class SolarPlant(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=100)
    capacity_kw = models.FloatField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.capacity_kw} kW)"


class SolarReading(models.Model):
    plant = models.ForeignKey(SolarPlant, on_delete=models.CASCADE, related_name='readings')
    timestamp = models.DateTimeField(auto_now_add=True)
    power_kw = models.FloatField()
    battery_percentage = models.FloatField()
    grid_export_kw = models.FloatField()

    class Meta:
        ordering = ['-timestamp']  # Latest first

    def __str__(self):
        return f"{self.plant.name} - {self.power_kw} kW"