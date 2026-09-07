import uuid

from django.conf import settings
from django.db import models

from apps.catalog.models import Product


class VendorWarehouse(models.Model):
    """
    A vendor's physical stock location. Most small vendors will only ever
    have one (their shop) — this is purely opt-in: StockBatch.warehouse is
    nullable, so a vendor never has to set one up to use inventory at all.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey("vendors.Vendor", related_name="warehouses", on_delete=models.CASCADE)
    name = models.CharField(max_length=100, help_text="e.g. 'Main shop', 'Cold storage', 'Backup godown'")
    address_line = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vendor_warehouses"
        ordering = ["-is_default", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor"], condition=models.Q(is_default=True), name="one_default_vendor_warehouse"
            )
        ]

    def __str__(self):
        return f"{self.vendor.shop_name} — {self.name}"

    def save(self, *args, **kwargs):
        if self.is_default:
            VendorWarehouse.objects.filter(vendor_id=self.vendor_id).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class StockBatch(models.Model):
    """
    One incoming purchase/batch of a product. Enables expiry tracking
    (critical for grocery/medical/bakery/meat) and purchase-price history.
    Product.stock_quantity is the fast-path total; this table is the detail
    behind it — kept in sync via the viewset on create/delete.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, related_name="stock_batches", on_delete=models.CASCADE)
    warehouse = models.ForeignKey(
        VendorWarehouse, related_name="stock_batches", null=True, blank=True, on_delete=models.SET_NULL,
        help_text="Optional — which physical location this batch is stored at",
    )
    batch_number = models.CharField(max_length=50, blank=True)
    quantity = models.PositiveIntegerField()
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Cost price per unit for this batch")
    supplier_name = models.CharField(max_length=150, blank=True)
    expiry_date = models.DateField(null=True, blank=True, help_text="Leave blank for non-perishables (electronics, clothing)")
    received_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_batches"
        ordering = ["expiry_date", "-created_at"]
        indexes = [models.Index(fields=["product", "expiry_date"])]

    def __str__(self):
        return f"{self.product.name} batch {self.batch_number or self.id} ({self.quantity})"

    @property
    def is_expired(self):
        from django.utils import timezone

        return bool(self.expiry_date and self.expiry_date < timezone.localdate())


class StockMovement(models.Model):
    """
    Audit ledger of every change to a product's stock_quantity — purchases
    (batch received), sales (checkout), returns (order cancelled), and
    manual adjustments (damage, recount correction, etc).

    Only 'adjustment' entries can be edited or deleted — sale/return/purchase
    rows are a record of something that actually happened elsewhere in the
    system (an order, a batch) and editing them would desync the ledger from
    reality, so those stay append-only.
    """

    class MovementType(models.TextChoices):
        PURCHASE = "purchase", "Purchase (batch received)"
        SALE = "sale", "Sale"
        RETURN = "return", "Return / cancellation"
        ADJUSTMENT = "adjustment", "Manual adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, related_name="stock_movements", on_delete=models.CASCADE)
    movement_type = models.CharField(max_length=12, choices=MovementType.choices)
    quantity_delta = models.IntegerField(help_text="Positive = stock added, negative = stock removed")
    resulting_stock = models.PositiveIntegerField(help_text="Product.stock_quantity right after this movement")
    reference = models.CharField(max_length=100, blank=True, help_text="e.g. order number or batch number")
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_movements"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["product", "movement_type"])]

    def __str__(self):
        return f"{self.product.name}: {self.quantity_delta:+d} ({self.movement_type})"
