import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify

from apps.vendors.models import Vendor


class Category(models.Model):
    """
    Hierarchical product category — e.g. Grocery > Dairy > Milk.
    Distinct from vendors.ShopCategory (which classifies the shop itself);
    a single grocery shop sells products across many of these categories.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="subcategories", on_delete=models.CASCADE
    )
    icon = models.ImageField(upload_to="categories/", blank=True, null=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "categories"
        verbose_name_plural = "Categories"
        ordering = ["display_order", "name"]
        indexes = [models.Index(fields=["parent", "is_active"])]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.parent.name} > {self.name}" if self.parent else self.name


class Brand(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    logo = models.ImageField(upload_to="brands/", blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "brands"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    """
    One sellable item at one vendor. Simple flat stock model for now
    (stock_quantity on the product) — batch/expiry-level tracking is added
    in apps.inventory during the vendor-panel phase.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, related_name="products", on_delete=models.CASCADE)
    category = models.ForeignKey(Category, related_name="products", on_delete=models.PROTECT)
    brand = models.ForeignKey(Brand, related_name="products", null=True, blank=True, on_delete=models.SET_NULL)

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=30, help_text="e.g. 500 g, 1 L, 1 pc, 6 pcs")

    manufacturer_or_marketer = models.CharField(max_length=200, blank=True, help_text="Legal manufacturer/marketer name for the 'Information' card")
    country_of_origin = models.CharField(max_length=100, blank=True, default="India")
    shelf_life = models.CharField(max_length=50, blank=True, help_text="e.g. '24 months', '6 months' — leave blank for non-perishables")

    mrp = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    sku = models.CharField(max_length=50, blank=True)
    barcode = models.CharField(max_length=50, blank=True)

    stock_quantity = models.PositiveIntegerField(default=0)
    is_available = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    nutrition_info = models.JSONField(blank=True, null=True, help_text="e.g. {'calories': 250, 'protein_g': 8}")
    tags = models.JSONField(blank=True, null=True, help_text="List of search tags, e.g. ['organic', 'gluten-free']")

    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["vendor", "is_available"]),
            models.Index(fields=["category", "is_available"]),
            models.Index(fields=["is_featured"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)[:200] or "product"
            slug = base_slug
            # Same product name at different vendors is common and expected
            # (e.g. "Amul Milk 500ml" sold by many shops) — disambiguate with
            # a short random suffix instead of silently colliding.
            while Product.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.vendor.shop_name})"

    @property
    def discount_percent(self):
        if self.mrp and self.mrp > 0:
            return round((self.mrp - self.selling_price) / self.mrp * 100)
        return 0

    @property
    def in_stock(self):
        return self.is_available and self.stock_quantity > 0


class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="products/")
    is_primary = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "product_images"
        ordering = ["display_order"]

    def __str__(self):
        return f"Image for {self.product.name}"


class ProductAttribute(models.Model):
    """A spec/attribute row shown on the product detail page — e.g. 'Material: Cotton', 'Shelf life: 6 months'."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, related_name="attributes", on_delete=models.CASCADE)
    name = models.CharField(max_length=100, help_text="e.g. 'Material', 'Shelf life'")
    value = models.CharField(max_length=200, help_text="e.g. 'Cotton', '6 months'")
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "product_attributes"
        ordering = ["display_order"]

    def __str__(self):
        return f"{self.name}: {self.value}"


class ProductVariant(models.Model):
    """
    A separately buyable version of the same product — e.g. different pack
    sizes (500g / 1kg) or a color/size combo. Each has its own price and
    stock; the parent Product's own price/stock stay the 'default' option.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE)
    name = models.CharField(max_length=100, help_text="e.g. '1 kg', 'Red - Large'")
    sku = models.CharField(max_length=50, blank=True)
    mrp = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_available = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "product_variants"
        ordering = ["display_order"]

    def __str__(self):
        return f"{self.product.name} — {self.name}"

    @property
    def in_stock(self):
        return self.is_available and self.stock_quantity > 0


class Review(models.Model):
    """
    One review per (customer, product) — only from a customer with a
    DELIVERED order containing that product (checked in the serializer,
    not here, since it needs cross-app access to Order/OrderItem).
    Product.rating_avg/rating_count are recalculated whenever a review is
    created, updated, or deleted (see apps.catalog.signals).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, related_name="reviews", on_delete=models.CASCADE)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="product_reviews", on_delete=models.CASCADE
    )
    rating = models.PositiveSmallIntegerField(help_text="1-5 stars")
    comment = models.CharField(max_length=1000, blank=True)
    is_approved = models.BooleanField(default=True, help_text="Admin can unpublish without deleting")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reviews"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(check=models.Q(rating__gte=1, rating__lte=5), name="review_rating_1_to_5"),
        ]
        unique_together = ("product", "customer")
        indexes = [models.Index(fields=["product", "is_approved"])]

    def __str__(self):
        return f"{self.customer} rated {self.product.name}: {self.rating}★"
