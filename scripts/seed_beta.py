"""Idempotent seed data for beta/local environments. Never run against production."""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from operations.models import Service, User

services = [
    ("trousers.reduce_waist", "Reduce trouser waist", "trousers", 19900),
    ("trousers.shorten_length", "Shorten trouser length", "trousers", 14900),
    ("shirt.shorten_sleeve", "Shorten shirt sleeve", "shirt", 14900),
]
for code, name, garment_type, price in services:
    Service.objects.update_or_create(code=code, defaults={"name": name, "garment_type": garment_type, "base_price_paise": price, "measurement_schema": {"schema_version": 1, "required": ["measurement_mode"]}, "active": True})
for username, role in [("+919900000001", "admin"), ("+919900000002", "logistics"), ("+919900000003", "customer")]:
    User.objects.get_or_create(username=username, defaults={"phone": username, "role": role, "is_staff": role == "admin"})
print("Seeded StitchCore beta/local data")
