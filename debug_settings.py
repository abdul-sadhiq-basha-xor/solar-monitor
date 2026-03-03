import sys
print('Full sys.argv:', sys.argv)
print("'test' in sys.argv:", 'test' in sys.argv)
print()

# Now check what settings actually has
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','solar_monitor.settings')
import django
django.setup()

from django.conf import settings
print('Current DB ENGINE:', settings.DATABASES['default']['ENGINE'])
print('Current DB NAME:', settings.DATABASES['default'].get('NAME', 'N/A'))
