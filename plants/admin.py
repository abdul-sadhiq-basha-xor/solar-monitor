from django.contrib import admin
from .models import SolarPlant, SolarReading


class SolarReadingInline(admin.TabularInline):
    model = SolarReading
    extra = 0
    readonly_fields = ('timestamp',)


@admin.register(SolarPlant)
class SolarPlantAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'capacity_kw', 'owner')
    search_fields = ('name','location')
    inlines = (SolarReadingInline,)


@admin.register(SolarReading)
class SolarReadingAdmin(admin.ModelAdmin):
    list_display = ('plant', 'power_kw', 'battery_percentage', 'timestamp')
    list_filter = ('plant',)