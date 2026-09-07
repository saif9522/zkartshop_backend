import time

from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = "Waits for the database to be available before proceeding — avoids a startup race in Docker."

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=int, default=30, help="Max seconds to wait")

    def handle(self, *args, **options):
        self.stdout.write("Checking database connection...")
        deadline = time.time() + options["timeout"]
        conn = connections["default"]

        while time.time() < deadline:
            try:
                conn.cursor()
                self.stdout.write(self.style.SUCCESS("Database is ready."))
                return
            except OperationalError:
                self.stdout.write("Database unavailable, waiting 1 second...")
                time.sleep(1)

        self.stdout.write(self.style.WARNING("Database wait timed out — proceeding anyway."))
