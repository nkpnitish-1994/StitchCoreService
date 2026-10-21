"""One-off ECS migration task; PostgreSQL serializes concurrent deployments."""
from django.core.management import BaseCommand, call_command
from django.db import connection


class Command(BaseCommand):
    help = "Apply migrations under a PostgreSQL advisory lock."

    def handle(self, **options):
        if connection.vendor != "postgresql":
            call_command("migrate", interactive=False)
            return
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(784326951)")
            try:
                call_command("migrate", interactive=False)
            finally:
                cursor.execute("SELECT pg_advisory_unlock(784326951)")
