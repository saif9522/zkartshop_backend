import random
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField

from apps.accounts.managers import UserManager


class Role(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    VENDOR = "vendor", "Vendor"
    DELIVERY = "delivery", "Delivery partner"
    ADMIN = "admin", "Admin"
    SUPER_ADMIN = "super_admin", "Super admin"


class User(AbstractBaseUser, PermissionsMixin):
    """
    Single user table for every role in the platform. Role-specific data
    (shop details, vehicle details, etc.) lives in the related app's own
    model, linked one-to-one back to this User.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Nullable so a customer can sign up purely via Google before adding a phone.
    phone = PhoneNumberField(unique=True, region="IN", null=True, blank=True)
    email = models.EmailField(blank=True, null=True)
    full_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)

    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    google_id = models.CharField(max_length=64, blank=True, null=True, unique=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # Django admin site access
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(blank=True, null=True)

    referral_code = models.CharField(max_length=10, unique=True, blank=True, null=True, db_index=True)
    referred_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals_made"
    )

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
        indexes = [models.Index(fields=["role"])]

    def __str__(self):
        return f"{self.full_name or self.phone} ({self.role})"

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self._generate_referral_code()
        super().save(*args, **kwargs)

    def _generate_referral_code(self):
        import random
        import string

        while True:
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not User.objects.filter(referral_code=code).exists():
                return code

    @property
    def is_customer(self):
        return self.role == Role.CUSTOMER

    @property
    def is_vendor(self):
        return self.role == Role.VENDOR

    @property
    def is_delivery_partner(self):
        return self.role == Role.DELIVERY


class Address(models.Model):
    """Customer delivery addresses — also used by vendors for shop location."""

    class AddressType(models.TextChoices):
        HOME = "home", "Home"
        WORK = "work", "Work"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="addresses", on_delete=models.CASCADE)
    label = models.CharField(max_length=20, choices=AddressType.choices, default=AddressType.HOME)
    address_line = models.CharField(max_length=255)
    landmark = models.CharField(max_length=150, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, default="Jharkhand")
    pincode = models.CharField(max_length=6)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "addresses"
        indexes = [models.Index(fields=["user", "is_default"])]

    def __str__(self):
        return f"{self.label} - {self.address_line[:40]}"


class OTP(models.Model):
    """Short-lived OTP for phone login, signup verification, and password reset."""

    class Purpose(models.TextChoices):
        LOGIN = "login", "Login"
        SIGNUP = "signup", "Signup verification"
        RESET_PASSWORD = "reset_password", "Password reset"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = PhoneNumberField(region="IN")
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    is_used = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "otps"
        indexes = [models.Index(fields=["phone", "purpose", "is_used"])]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = f"{random.randint(0, 999999):06d}"
        if not self.expires_at:
            from django.conf import settings as dj_settings

            minutes = getattr(dj_settings, "OTP_EXPIRY_MINUTES", 5)
            self.expires_at = timezone.now() + timedelta(minutes=minutes)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    def is_valid(self, code):
        return not self.is_used and not self.is_expired and self.code == code
