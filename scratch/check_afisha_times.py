import django
import os
import sys
from django.utils import timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from api.models import Event

events = Event.objects.filter(provider__slug='afisha_md')
counts = {}
for e in events:
    if e.date_start:
        t = e.date_start.strftime('%H:%M')
        counts[t] = counts.get(t, 0) + 1

print(f"Time distribution: {counts}")
if counts.get('00:00'):
    print(f"Warning: {counts['00:00']} events have 00:00 time (local).")
if counts.get('03:00'):
    print(f"Warning: {counts['03:00']} events have 03:00 time (local).")
