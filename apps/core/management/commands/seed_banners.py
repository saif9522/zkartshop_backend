"""
Seeds the homepage hero slider (the big rotating banner) with promotional
images. Safe to run multiple times — matched by title, so re-running just
updates the image/link rather than creating duplicates.

Usage:
    python manage.py seed_banners
"""
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

BANNERS_DIR = Path(__file__).resolve().parents[4] / "seed_assets" / "banners"

# (filename, title, link_url, display_order)
# title is used only for admin bookkeeping — the images already have their
# own text baked in, so HeroSlider won't overlay anything extra on top.
BANNERS = [
    ("01_paan_corner.jpg", "zKart Corner — Smoking accessories", "/search?q=lighter", 1),
    ("02_groceries.jpg", "zKart Corner — Groceries", "/search?category=groceries", 2),
    ("03_beauty.jpg", "zKart Corner — Beauty", "/search?category=beauty", 3),
    ("04_beverages.jpg", "zKart Corner — Beverages", "/search?category=beverages", 4),
    ("05_toys.jpg", "zKart Corner — Toys", "/search?category=toys", 5),
    ("06_books.jpg", "zKart Corner — Books", "/search?category=books", 6),
    ("07_electronics.jpg", "zKart Corner — Electronics", "/search?category=electronics", 7),
]


class Command(BaseCommand):
    help = "Seeds the homepage hero slider with the zKart Corner promotional banners."

    def handle(self, *args, **options):
        from apps.marketing.models import Slider

        if not BANNERS_DIR.exists():
            self.stdout.write(self.style.ERROR(f"Banner assets not found at {BANNERS_DIR}"))
            return

        created, updated = 0, 0
        for filename, title, link_url, order in BANNERS:
            path = BANNERS_DIR / filename
            if not path.exists():
                self.stdout.write(self.style.WARNING(f"Skipping {filename} — file not found"))
                continue

            slider, was_created = Slider.objects.get_or_create(
                title=title, defaults={"link_url": link_url, "display_order": order, "is_active": True},
            )
            with open(path, "rb") as f:
                slider.image.save(filename, File(f), save=False)
            slider.link_url = link_url
            slider.display_order = order
            slider.is_active = True
            slider.save()

            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Banners seeded: {created} created, {updated} updated."))
