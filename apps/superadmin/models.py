import uuid

from django.conf import settings
from django.db import models


class City(models.Model):
    """
    A city the platform operates in. Delivery pricing here overrides the
    global DELIVERY_CHARGE/FREE_DELIVERY_THRESHOLD settings for vendors
    based in this city — null means "use the platform default."
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    state = models.CharField(max_length=100, default="Jharkhand")
    delivery_charge = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    free_delivery_threshold = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cities"
        verbose_name_plural = "Cities"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name}, {self.state}"


class Warehouse(models.Model):
    """A dark-store/fulfillment warehouse in a city — infrastructure for future warehouse-based fulfillment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    city = models.ForeignKey(City, related_name="warehouses", on_delete=models.CASCADE)
    address_line = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "warehouses"

    def __str__(self):
        return f"{self.name} ({self.city.name})"


class PlatformSettings(models.Model):
    """
    Singleton row (always pk=1) — platform-wide defaults super admin can
    tune at runtime instead of editing .env and redeploying. City-level
    overrides (above) take precedence over these when set.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    default_commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    default_delivery_charge = models.DecimalField(
        max_digits=6, decimal_places=2, default=25, help_text="Base charge, covers the first delivery_free_km"
    )
    default_free_delivery_threshold = models.DecimalField(max_digits=8, decimal_places=2, default=299)
    delivery_free_km = models.DecimalField(
        max_digits=5, decimal_places=2, default=3, help_text="Distance covered by the base charge before per-km pricing kicks in"
    )
    delivery_per_km_charge = models.DecimalField(
        max_digits=6, decimal_places=2, default=8, help_text="Extra charge per km beyond delivery_free_km"
    )
    max_delivery_radius_km = models.DecimalField(
        max_digits=5, decimal_places=2, default=12, help_text="Orders from vendors beyond this distance are blocked at checkout"
    )
    order_accept_timeout_minutes = models.PositiveSmallIntegerField(default=5)
    maintenance_mode = models.BooleanField(default=False)
    referral_bonus_referrer = models.DecimalField(
        max_digits=8, decimal_places=2, default=50, help_text="Wallet credit for the person who referred"
    )
    referral_bonus_referred = models.DecimalField(
        max_digits=8, decimal_places=2, default=50, help_text="Wallet credit for the new signup"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # the singleton is never deleted

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Platform settings"


class BackupLog(models.Model):
    """Tracks each database backup run, triggered on-demand or via a scheduled job."""

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.CharField(max_length=255, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    error_message = models.TextField(blank=True)
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "backup_logs"
        ordering = ["-started_at"]

    def __str__(self):
        return f"Backup {self.started_at:%Y-%m-%d %H:%M} ({self.status})"


class StaffPermission(models.Model):
    """
    Fine-grained RBAC for admin-role staff. super_admin always has full
    access regardless of these flags; these only scope down what an
    'admin' role user can do within the admin panel.
    """

    class Department(models.TextChoices):
        CUSTOM = "custom", "Custom (pick sections manually)"
        FULL = "full", "Full access"
        ACCOUNTS = "accounts", "Accounts / Finance"
        VENDOR_DESK = "vendor_desk", "Vendor desk"
        DELIVERY_DESK = "delivery_desk", "Delivery desk"
        CATALOG = "catalog", "Catalog / Products"
        SUPPORT = "support", "Customer support"

    # Which section flags each department turns on. Anything not listed = False.
    DEPARTMENT_PRESETS = {
        Department.FULL: {
            "can_manage_vendors", "can_manage_delivery_partners", "can_manage_orders",
            "can_manage_coupons", "can_manage_categories", "can_manage_users", "can_view_reports",
        },
        Department.ACCOUNTS: {"can_view_reports", "can_manage_orders"},
        Department.VENDOR_DESK: {"can_manage_vendors", "can_manage_orders"},
        Department.DELIVERY_DESK: {"can_manage_delivery_partners", "can_manage_orders"},
        Department.CATALOG: {"can_manage_categories", "can_manage_coupons"},
        Department.SUPPORT: {"can_manage_users", "can_manage_orders"},
    }

    FLAG_FIELDS = [
        "can_manage_vendors", "can_manage_delivery_partners", "can_manage_orders",
        "can_manage_coupons", "can_manage_categories", "can_manage_users", "can_view_reports",
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="staff_permission", on_delete=models.CASCADE)
    department = models.CharField(
        max_length=20, choices=Department.choices, default=Department.CUSTOM,
        help_text="Pick a department to auto-set the sections below, or 'Custom' to choose them yourself",
    )
    can_manage_vendors = models.BooleanField(default=False)
    can_manage_delivery_partners = models.BooleanField(default=False)
    can_manage_orders = models.BooleanField(default=False)
    can_manage_coupons = models.BooleanField(default=False)
    can_manage_categories = models.BooleanField(default=False)
    can_manage_users = models.BooleanField(default=False)
    can_view_reports = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "staff_permissions"

    def __str__(self):
        return f"Permissions for {self.user}"

    def apply_department_preset(self):
        """If a non-custom department is set, overwrite the section flags to match it."""
        if self.department and self.department != self.Department.CUSTOM:
            enabled = self.DEPARTMENT_PRESETS.get(self.department, set())
            for flag in self.FLAG_FIELDS:
                setattr(self, flag, flag in enabled)
