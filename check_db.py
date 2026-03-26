import os
import sys
import django
print('sys.argv before settings:', sys.argv)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','solar_monitor.settings')
django.setup()
from django.conf import settings
from plants.models import CSVUpload
print('DATABASES:', settings.DATABASES)
print('ENGINE', settings.DATABASES['default']['ENGINE'])
print('NAME', settings.DATABASES['default']['NAME'])
print('uploads', CSVUpload.objects.count())
