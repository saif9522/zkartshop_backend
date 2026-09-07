"""
Some imported product descriptions (from copy-pasted Amazon/scraped
listings) contain the *raw HTML source* as literal text instead of clean
copy — showing up as visible <div class="..."> markup on the product page
instead of a readable description.

This command re-processes every product whose description looks like HTML:
1. Extracts clean, readable text for the description (no visible tags).
2. If the source has a technical-spec table (key/value rows — "Brand",
   "RAM Size", "Processor", etc), pulls those into ProductAttribute rows
   so the frontend's Highlights card can show them structured.
3. If an "Additional Information" style table has Manufacturer/Country of
   Origin/Shelf Life, fills those onto the product for the Information card.

Safe to re-run — attributes are replaced (not duplicated) each time.

Usage:
    python manage.py clean_imported_descriptions
    python manage.py clean_imported_descriptions --dry-run
"""
import re

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

INFO_FIELD_MAP = {
    "manufacturer": "manufacturer_or_marketer",
    "packer": "manufacturer_or_marketer",
    "importer": "manufacturer_or_marketer",
    "country of origin": "country_of_origin",
    "shelf life": "shelf_life",
}

SKIP_LABELS = {"asin", "customer reviews", "best sellers rank", "date first available"}


INVISIBLE_CHARS = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")


def clean_text_value(text):
    return INVISIBLE_CHARS.sub("", text).strip()


def looks_like_html(text):
    return bool(text) and "<" in text and ">" in text and re.search(r"<[a-z][\s\S]*?>", text, re.IGNORECASE)


def extract_clean_text(soup):
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [clean_text_value(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n\n".join(lines)


def extract_spec_rows(soup):
    rows = []
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        label = clean_text_value(cells[0].get_text(strip=True))
        value = clean_text_value(cells[1].get_text(" ", strip=True))
        if not label or not value:
            continue
        if label.lower() in SKIP_LABELS:
            continue
        rows.append((label, value[:200]))
    return rows


class Command(BaseCommand):
    help = "Cleans up product descriptions that contain raw HTML from a scraped/copy-pasted listing."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would change without saving")

    def handle(self, *args, **options):
        from apps.catalog.models import Product, ProductAttribute

        dry_run = options["dry_run"]
        candidates = [p for p in Product.objects.all() if looks_like_html(p.description)]
        self.stdout.write(f"Found {len(candidates)} products with HTML-contaminated descriptions.")

        cleaned = attrs_added = info_filled = 0

        for product in candidates:
            soup = BeautifulSoup(product.description, "html.parser")
            clean_text = extract_clean_text(soup)
            spec_rows = extract_spec_rows(soup)

            update_fields = []
            if clean_text and clean_text != product.description:
                if not dry_run:
                    product.description = clean_text[:8000]
                update_fields.append("description")
                cleaned += 1

            new_attributes = []
            for label, value in spec_rows:
                field_name = INFO_FIELD_MAP.get(label.lower())
                if field_name:
                    if not dry_run:
                        setattr(product, field_name, value)
                    if field_name not in update_fields:
                        update_fields.append(field_name)
                    info_filled += 1
                else:
                    new_attributes.append((label, value))

            if update_fields and not dry_run:
                product.save(update_fields=update_fields)

            if new_attributes and not dry_run:
                product.attributes.all().delete()
                ProductAttribute.objects.bulk_create([
                    ProductAttribute(product=product, name=label[:100], value=value[:200], display_order=i)
                    for i, (label, value) in enumerate(new_attributes[:25])
                ])
                attrs_added += len(new_attributes[:25])

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no changes saved."))
        self.stdout.write(self.style.SUCCESS(
            f"Descriptions cleaned: {cleaned}. Attribute rows extracted: {attrs_added}. "
            f"Information-card fields filled: {info_filled}."
        ))
