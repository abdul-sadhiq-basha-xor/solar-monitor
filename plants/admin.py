from django.contrib import admin
from .models import SolarPlant, SolarReading, CSVUpload, FailedTask


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


@admin.register(CSVUpload)
class CSVUploadAdmin(admin.ModelAdmin):
    list_display = ('file_name', 'plant', 'status', 'progress_percent', 'created_at')
    list_filter = ('status', 'created_at')
    readonly_fields = ('task_id', 'rows_processed', 'total_rows', 'successes', 'errors', 'created_at', 'completed_at')
    search_fields = ('file_name', 'plant__name')


@admin.register(FailedTask)
class FailedTaskAdmin(admin.ModelAdmin):
    list_display = ('task_name', 'task_id', 'retry_count', 'resolved', 'failed_at')
    list_filter = ('resolved', 'failed_at')
    readonly_fields = ('task_id', 'task_name', 'args', 'error_message', 'retry_count', 'failed_at')
    search_fields = ('task_name', 'task_id')
    actions = ['mark_resolved']
    
    def mark_resolved(self, request, queryset):
        """Admin action to mark failed tasks as resolved."""
        from django.utils import timezone
        count = queryset.update(resolved=True, resolved_at=timezone.now())
        self.message_user(request, f'{count} task(s) marked as resolved.')
    mark_resolved.short_description = 'Mark selected tasks as resolved'