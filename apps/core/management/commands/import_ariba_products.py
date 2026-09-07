"""
Imports the ~1124 products exported from the Ariba Mart WooCommerce store
(seed_assets/ariba_products.json) into the catalog — real product names,
descriptions, MRP/selling price (from WooCommerce's regular/sale price),
and category.

Image files are NOT included here — this only sets the *expected* file path
(`products/<original-filename>`) on each product's image record, matching
Product.images upload_to="products/". Drop the actual image files into
`media/products/` (matching filenames) and they'll show up automatically —
no re-import needed.

Safe to re-run: matches existing products by name within the Ariba Mart
vendor, so re-running updates rather than duplicates.

Usage:
    python manage.py import_ariba_products
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

DATA_FILE = Path(__file__).resolve().parents[4] / "seed_assets" / "ariba_products.json"


class Command(BaseCommand):
    help = "Imports products from the Ariba Mart export (seed_assets/ariba_products.json)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--vendor-phone", default="+919471500119",
            help="Phone number for the Ariba Mart vendor account (created if it doesn't exist)",
        )

    def handle(self, *args, **options):
        from apps.accounts.models import User
        from apps.catalog.models import Category, Product, ProductImage
        from apps.vendors.models import ShopCategory, Vendor

        if not DATA_FILE.exists():
            self.stdout.write(self.style.ERROR(f"Data file not found: {DATA_FILE}"))
            return

        with open(DATA_FILE, encoding="utf-8") as f:
            products_data = json.load(f)
        self.stdout.write(f"Loaded {len(products_data)} products from export.")

        phone = options["vendor_phone"]
        owner, owner_created = User.objects.get_or_create(
            phone=phone,
            defaults={"full_name": "Ariba Mart", "email": "aribamart03@gmail.com", "role": "vendor"},
        )
        if owner_created:
            owner.set_unusable_password()
            owner.save(update_fields=["password"])

        vendor, vendor_created = Vendor.objects.get_or_create(
            owner=owner,
            defaults={
                "shop_name": "Ariba Mart", "business_name": "Ariba Mart Retail Private Limited",
                "whatsapp_number": phone, "category": ShopCategory.GROCERY,
                "address_line": "S.S.J.S. Namdhari College", "city": "Garhwa", "state": "Jharkhand",
                "pincode": "822114", "country": "India", "latitude": "24.1553", "longitude": "83.8099",
                "status": "approved", "is_open": True,
            },
        )
        self.stdout.write(f"Vendor: {vendor.shop_name} ({'created' if vendor_created else 'existing'})")

        category_cache = {}

        def get_category(name):
            name = (name or "Uncategorized").strip() or "Uncategorized"
            if name not in category_cache:
                category, _ = Category.objects.get_or_create(name=name)
                category_cache[name] = category
            return category_cache[name]

        created_count = updated_count = skipped_count = 0

        for item in products_data:
            name = (item.get("title") or "").strip()
            selling_price = item.get("selling_price")
            if not name or not selling_price:
                skipped_count += 1
                continue

            mrp = item.get("mrp") or selling_price
            category = get_category((item.get("categories") or ["Uncategorized"])[0])
            stock_status = item.get("stock_status")
            stock_quantity = item.get("stock_quantity")

            product, was_created = Product.objects.update_or_create(
                vendor=vendor, name=name,
                defaults={
                    "category": category,
                    "description": item.get("description") or item.get("short_description") or "",
                    "unit": "1 pc",
                    "mrp": mrp,
                    "selling_price": selling_price,
                    "sku": (item.get("sku") or "")[:50],
                    "stock_quantity": int(stock_quantity) if stock_quantity else 50,
                    "is_available": stock_status != "outofstock",
                },
            )

            image_filename = item.get("image_filename")
            if image_filename and not product.images.exists():
                image = ProductImage(product=product, is_primary=True)
                image.image.name = f"products/{image_filename}"
                image.save()

            if was_created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done — {created_count} created, {updated_count} updated, {skipped_count} skipped "
            f"(missing name/price). {len(category_cache)} categories."
        ))
        self.stdout.write(
            "Now copy your product image files into backend/media/products/ — "
            "filenames must match what WooCommerce had (the import already recorded the expected names)."
        )
