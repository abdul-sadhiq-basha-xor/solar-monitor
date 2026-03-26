from django_celery_beat.schedulers import DatabaseScheduler
from django.utils import timezone

# Add at top of scheduler.py outside the class
print("✅ TimeInjectingScheduler MODULE LOADED")

class TimeInjectingScheduler(DatabaseScheduler):
    def apply_async(self, entry, producer=None, advance=True, **kwargs):
        print(f"✅ apply_async CALLED for {entry.task}")
        # compute the intended run time rather than current moment
        try:
            # many schedule objects (crontab, interval, solar) implement next_run_at
            next_run = entry.schedule.next_run_at(entry.last_run_at)
            if next_run is None:
                raise AttributeError("next_run is None")
            beat_time_iso = next_run.isoformat()
        except Exception as e:
            # fallback: use current time
            print(f"⚠️ could not determine next_run_at: {e}, using now")
            beat_time_iso = timezone.now().isoformat()

        entry_kwargs = entry.kwargs or {}
        entry_kwargs['beat_time_iso'] = beat_time_iso
        entry.kwargs = entry_kwargs
        print(f"✅ kwargs set: {entry.kwargs}")
        return super().apply_async(entry, producer=producer, advance=advance, **kwargs)