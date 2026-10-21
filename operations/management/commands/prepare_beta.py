import os
from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction
from operations.models import Service, User, Vendor


class Command(BaseCommand):
    help = "Migrate beta and provision restricted test accounts from injected secrets."

    def handle(self, **options):
        if settings.STITCHCORE_ENV != "beta":
            raise CommandError("This command only runs in beta.")
        passwords = {name: os.environ.get(key) for name, key in (
            ("beta-admin", "BETA_ADMIN_PASSWORD"), ("beta-customer", "BETA_CUSTOMER_PASSWORD"))}
        if not all(passwords.values()):
            raise CommandError("Beta access secrets are missing.")
        call_command("migrate_locked")
        with transaction.atomic():
            for name, password in passwords.items():
                admin = name == "beta-admin"
                user, _ = User.objects.get_or_create(username=name, defaults={
                    "role": "admin" if admin else "customer", "is_staff": admin,
                    "is_superuser": admin, "first_name": "Beta admin" if admin else "Beta customer",
                })
                if not user.check_password(password):
                    user.set_password(password)
                    user.save(update_fields=["password"])
            for code, name, kind, price in [
                ("trousers.reduce_waist", "Reduce trouser waist", "trousers", 19900),
                ("trousers.shorten_length", "Shorten trouser length", "trousers", 14900),
                ("shirt.shorten_sleeve", "Shorten shirt sleeve", "shirt", 14900),
            ]:
                Service.objects.get_or_create(code=code, defaults={
                    "name": name, "garment_type": kind, "base_price_paise": price,
                    "measurement_schema": {"schema_version": 1},
                })
            Vendor.objects.get_or_create(name="Beta alteration partner", defaults={
                "phone": "+919900000010", "address": "Synthetic beta vendor; not a live service location",
            })
            partner, created = User.objects.get_or_create(username="beta-logistics", defaults={
                "role": "logistics", "first_name": "Beta logistics", "phone": "+919900000011",
            })
            if created:
                partner.set_unusable_password()
                partner.save(update_fields=["password"])
        self.stdout.write("Beta schema, catalogue, and restricted accounts are ready. No credentials logged.")
