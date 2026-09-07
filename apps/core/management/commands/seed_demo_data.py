"""
Seeds the database with demo data so the storefront (and the super-admin
console) isn't empty on a fresh setup: categories with icons, a demo vendor,
products with images, and a super-admin login. Safe to run multiple times
(uses get_or_create throughout).

Usage:
    python manage.py seed_demo_data
"""
import io
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand


# One flat colour per category/product so placeholder images are at least
# visually distinct in the admin/storefront until real photos are uploaded.
_PALETTE = [
    (46, 125, 50), (239, 108, 0), (2, 119, 189), (198, 40, 40),
    (106, 27, 154), (0, 121, 107), (255, 143, 0), (48, 63, 159),
]


def _placeholder_image(label: str, seed: int, size=(600, 600)) -> ContentFile:
    """Generates a simple flat-colour PNG with the label text, entirely offline."""
    from PIL import Image, ImageDraw, ImageFont

    color = _PALETTE[seed % len(_PALETTE)]
    img = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
    except OSError:
        font = ImageFont.load_default()

    # Word-wrap the label to fit the canvas width.
    words, lines, current = label.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) > size[0] - 60:
            lines.append(current)
            current = word
        else:
            current = trial
    lines.append(current)

    total_h = len(lines) * 50
    y = (size[1] - total_h) // 2
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((size[0] - w) / 2, y), line, fill="white", font=font)
        y += 50

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return ContentFile(buffer.getvalue())


class Command(BaseCommand):
    help = "Seed demo categories (with icons), a vendor, products (with images), and a super-admin login."

    def handle(self, *args, **options):
        from apps.accounts.models import Role, User
        from apps.catalog.models import Brand, Category, Product, ProductImage
        from apps.vendors.models import ShopCategory, Vendor

        self.stdout.write("Seeding demo data...")

        # --- Categories (+ generated icon if missing) --------------------------
        def make_category(name, parent=None, order=0, seed=0):
            cat, _ = Category.objects.get_or_create(name=name, parent=parent, defaults={"display_order": order})
            if not cat.icon:
                cat.icon.save(f"{cat.slug}.png", _placeholder_image(name, seed), save=True)
            return cat

        grocery = make_category("Grocery", order=1, seed=0)
        dairy = make_category("Dairy", parent=grocery, order=1, seed=1)
        fruits_veg = make_category("Fruits & Vegetables", order=2, seed=2)
        bakery = make_category("Bakery", order=3, seed=3)
        medical = make_category("Medical", order=4, seed=4)
        beverages = make_category("Beverages", order=5, seed=5)

        # --- Brand ------------------------------------------------------------
        amul, _ = Brand.objects.get_or_create(name="Amul")

        # --- Demo vendor (approved so products show up immediately) ----------
        owner, created = User.objects.get_or_create(
            phone="+919812300001",
            defaults={"role": Role.VENDOR, "full_name": "Ramesh Kirana", "is_phone_verified": True},
        )
        if created:
            owner.set_password("vendorpass123")
            owner.save()

        vendor, _ = Vendor.objects.get_or_create(
            owner=owner,
            defaults={
                "shop_name": "Ramesh Kirana Store",
                "category": ShopCategory.GROCERY,
                "status": Vendor.Status.APPROVED,
                "address_line": "Main Road, Garhwa",
                "city": "Garhwa",
                "latitude": Decimal("24.1553"),
                "longitude": Decimal("83.8099"),
            },
        )
        if vendor.status != Vendor.Status.APPROVED:
            vendor.status = Vendor.Status.APPROVED
            vendor.save(update_fields=["status"])

        # --- Demo super-admin login (for the super-admin console) -------------
        admin_user, admin_created = User.objects.get_or_create(
            phone="+919812399999",
            defaults={"role": Role.SUPER_ADMIN, "full_name": "Platform Admin", "is_phone_verified": True},
        )
        if admin_created:
            admin_user.set_password("adminpass123")
            admin_user.save()

        # --- Demo customer login (for the main storefront — cart/checkout are
        # customer-only; the vendor/admin logins above will get a 403 if used
        # to add to cart, that's expected, not a bug) ---------------------
        customer_user, customer_created = User.objects.get_or_create(
            phone="+919812311111",
            defaults={"role": Role.CUSTOMER, "full_name": "Test Customer", "is_phone_verified": True},
        )
        if customer_created:
            customer_user.set_password("customerpass123")
            customer_user.save()

        # --- Products (+ generated primary image if it has none) --------------
        products = [
            dict(category=dairy, brand=amul, name="Amul Toned Milk", unit="500 ml",
                 mrp="30.00", selling_price="27.00", stock_quantity=50, is_featured=True),
            dict(category=grocery, name="Tata Salt", unit="1 kg",
                 mrp="25.00", selling_price="22.00", stock_quantity=100, is_featured=True),
            dict(category=grocery, name="Aashirvaad Atta", unit="5 kg",
                 mrp="260.00", selling_price="235.00", stock_quantity=40, is_featured=True),
            dict(category=fruits_veg, name="Fresh Bananas", unit="1 dozen",
                 mrp="60.00", selling_price="50.00", stock_quantity=30),
            dict(category=fruits_veg, name="Onions", unit="1 kg",
                 mrp="35.00", selling_price="30.00", stock_quantity=80),
            dict(category=bakery, name="Whole Wheat Bread", unit="400 g",
                 mrp="45.00", selling_price="40.00", stock_quantity=25),
            dict(category=medical, name="Dolo 650 (Strip of 15)", unit="1 strip",
                 mrp="30.00", selling_price="28.00", stock_quantity=60),
            dict(category=beverages, name="Organic Coconut Milk", unit="1 pc (200 ml)",
                 description="Thick and creamy texture, no added sugar, made from fresh coconuts.",
                 mrp="89.00", selling_price="80.00", stock_quantity=45, is_featured=True),
        ]

        created_count = 0
        for i, p in enumerate(products):
            name = p["name"]
            fields = {k: v for k, v in p.items() if k != "name"}
            product, was_created = Product.objects.get_or_create(vendor=vendor, name=name, defaults=fields)
            created_count += int(was_created)
            if not product.images.exists():
                image = ProductImage.objects.create(product=product, is_primary=True)
                image.image.save(f"{product.slug}.png", _placeholder_image(name, i), save=True)

        self.stdout.write(self.style.SUCCESS(
            f"Done.\n"
            f"  Customer login (main app — shopping/cart/checkout): +919812311111 / customerpass123\n"
            f"  Vendor login (main app):                            +919812300001 / vendorpass123\n"
            f"  Super-admin login (super-admin console):            +919812399999 / adminpass123\n"
            f"  {created_count} new product(s) created "
            f"({Product.objects.filter(vendor=vendor).count()} total for this vendor)."
        ))
