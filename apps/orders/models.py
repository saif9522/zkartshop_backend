import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.accounts.models import Address
from apps.catalog.models import Product
from apps.vendors.models import Vendor


class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        FLAT = "flat", "Flat amount off"
        PERCENT = "percent", "Percentage off"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    max_discount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Cap for percent-type discounts, e.g. up to ₹50 off",
    )
    min_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    usage_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Blank = unlimited")
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "coupons"

    def __str__(self):
        return self.code

    def is_valid_now(self):
        now = timezone.now()
        if not self.is_active or not (self.valid_from <= now <= self.valid_to):
            return False
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return False
        return True

    def calculate_discount(self, subtotal):
        if subtotal < self.min_order_value:
            return 0
        if self.discount_type == self.DiscountType.FLAT:
            discount = self.discount_value
        else:
            discount = subtotal * self.discount_value / 100
            if self.max_discount is not None:
                discount = min(discount, self.max_discount)
        return min(discount, subtotal)


class Order(models.Model):
    """
    One vendor's fulfillment of a customer's checkout. A cart spanning
    multiple vendors is split into one Order per vendor at checkout time —
    each shop packs and hands off its own order independently.
    """

    class Status(models.TextChoices):
        PLACED = "placed", "Placed"
        ACCEPTED = "accepted", "Accepted"
        PACKING = "packing", "Packing"
        READY = "ready", "Ready for pickup"
        PICKUP = "pickup", "Picked up"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        NEARBY = "nearby", "Nearby"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentMethod(models.TextChoices):
        COD = "cod", "Cash on delivery"
        RAZORPAY = "razorpay", "Razorpay (card/UPI/netbanking)"
        WALLET = "wallet", "Wallet"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    # Transitions a vendor may trigger themselves through the vendor panel.
    VENDOR_TRANSITIONS = {
        Status.PLACED: [Status.ACCEPTED, Status.CANCELLED],
        Status.ACCEPTED: [Status.PACKING, Status.CANCELLED],
        Status.PACKING: [Status.READY, Status.CANCELLED],
        Status.READY: [Status.CANCELLED],
    }
    # Full lifecycle map — PICKUP onward is owned by the delivery app (Phase 6),
    # kept here so the state machine is defined in one place.
    ALL_TRANSITIONS = {
        **VENDOR_TRANSITIONS,
        Status.READY: [Status.PICKUP, Status.CANCELLED],
        Status.PICKUP: [Status.OUT_FOR_DELIVERY],
        Status.OUT_FOR_DELIVERY: [Status.NEARBY],
        Status.NEARBY: [Status.DELIVERED],
        Status.DELIVERED: [],
        Status.CANCELLED: [],
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="orders", on_delete=models.PROTECT)
    vendor = models.ForeignKey(Vendor, related_name="orders", on_delete=models.PROTECT)
    delivery_address = models.ForeignKey(Address, related_name="orders", on_delete=models.PROTECT)
    delivery_partner = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="deliveries", null=True, blank=True, on_delete=models.SET_NULL
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLACED)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    razorpay_order_id = models.CharField(max_length=64, blank=True)
    razorpay_payment_id = models.CharField(max_length=64, blank=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    extra_charges_total = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Sum of admin-configured extra charges (handling/packing/night/rain) applied to this order",
    )
    extra_charges_breakdown = models.JSONField(
        default=list, blank=True,
        help_text="List of {code, label, amount} for each extra charge applied, snapshotted at order time",
    )
    coupon_code = models.CharField(max_length=30, blank=True)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2)

    delivery_otp = models.CharField(max_length=6, blank=True, help_text="Shown to the customer; delivery partner enters this to confirm final delivery")
    pickup_otp = models.CharField(max_length=6, blank=True, help_text="Shown to the vendor; delivery partner enters this to confirm pickup from the shop")
    cancel_reason = models.CharField(max_length=255, blank=True)

    placed_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "orders"
        ordering = ["-placed_at"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["vendor", "status"]),
        ]

    def __str__(self):
        return f"{self.order_number} ({self.vendor.shop_name})"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"MOG{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def can_transition_to(self, new_status, *, vendor_initiated=False):
        allowed = (self.VENDOR_TRANSITIONS if vendor_initiated else self.ALL_TRANSITIONS).get(self.status, [])
        return new_status in allowed


class OrderItem(models.Model):
    """
    Snapshots product name/unit/price at order time so historical orders
    stay accurate even if the vendor later edits or deletes the product.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name="+", null=True, on_delete=models.SET_NULL)
    product_name = models.CharField(max_length=200)
    unit = models.CharField(max_length=30)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

    class Meta:
        db_table = "order_items"

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"

    @property
    def subtotal(self):
        return self.price * self.quantity


class OrderStatusHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, related_name="status_history", on_delete=models.CASCADE)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "order_status_history"
        ordering = ["changed_at"]

    def __str__(self):
        return f"{self.order.order_number}: {self.from_status} → {self.to_status}"


class PaymentMethodConfig(models.Model):
    """
    Admin-managed toggle for each payment method — e.g. temporarily disable
    COD, or Razorpay if the gateway is down. Order.PaymentMethod stays the
    enum of methods the *system* knows how to process; this table controls
    which of those are actually offered to customers right now.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, choices=Order.PaymentMethod.choices, unique=True)
    label = models.CharField(max_length=100, blank=True, help_text="Override display label (optional)")
    is_enabled = models.BooleanField(default=True)
    extra_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0, help_text="e.g. COD handling fee")
    min_order_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "payment_method_configs"
        ordering = ["display_order"]

    def __str__(self):
        return self.label or self.get_code_display()


class ExtraCharge(models.Model):
    """
    Admin-configurable extra charges added at checkout — handling, packing,
    night, rain, or any custom fee. A charge is only ever applied (and only
    shown to the customer) while `is_active` is True, so nothing appears until
    an admin actually adds/enables it.

    Optional conditions:
      * time window (active_from_hour/active_to_hour) — e.g. a night charge that
        only applies between 22:00 and 06:00. Leave both blank = applies any time.
      * min_order_value — only apply above a certain cart value.
      * for percentage charges, max_charge caps the amount.
    """

    class ChargeType(models.TextChoices):
        FLAT = "flat", "Flat amount"
        PERCENT = "percent", "Percentage of subtotal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=40, unique=True, help_text="Internal key, e.g. handling / packing / night / rain")
    label = models.CharField(max_length=100, help_text="Shown to the customer, e.g. 'Packing charge'")
    charge_type = models.CharField(max_length=10, choices=ChargeType.choices, default=ChargeType.FLAT)
    amount = models.DecimalField(max_digits=8, decimal_places=2, help_text="Rupees for flat, or percent for percentage")
    max_charge = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Cap for percentage charges (ignored for flat)",
    )
    min_order_value = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Only apply when the order subtotal is at least this",
    )
    active_from_hour = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="0–23. Start of the hours this applies (e.g. 22 for a night charge). Blank = any time",
    )
    active_to_hour = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="0–23. End hour (exclusive). May wrap past midnight, e.g. from 22 to 6",
    )
    is_active = models.BooleanField(default=True, help_text="Master switch — a rain charge is simply toggled on when it's raining")
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "extra_charges"
        ordering = ["display_order", "label"]

    def __str__(self):
        return f"{self.label} ({self.get_charge_type_display()})"

    def applies_now(self, subtotal, at_time=None):
        from django.utils import timezone

        if not self.is_active:
            return False
        if self.min_order_value is not None and subtotal < self.min_order_value:
            return False
        if self.active_from_hour is not None and self.active_to_hour is not None:
            hour = (at_time or timezone.localtime()).hour
            start, end = self.active_from_hour, self.active_to_hour
            in_window = start <= hour < end if start <= end else (hour >= start or hour < end)
            if not in_window:
                return False
        return True

    def compute_amount(self, subtotal):
        from decimal import Decimal

        if self.charge_type == self.ChargeType.PERCENT:
            amount = (Decimal(str(subtotal)) * self.amount / 100)
            if self.max_charge is not None:
                amount = min(amount, self.max_charge)
        else:
            amount = self.amount
        return Decimal(str(amount)).quantize(Decimal("0.01"))
