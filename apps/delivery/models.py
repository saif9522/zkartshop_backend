import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models

from apps.core.encrypted_fields import EncryptedCharField

DOCUMENT_EXTENSIONS = ["png", "jpg", "jpeg", "webp", "pdf"]
_doc_validator = FileExtensionValidator(allowed_extensions=DOCUMENT_EXTENSIONS)


class DeliveryProfile(models.Model):
    """One row per delivery-role user — vehicle details, verification, live status."""

    class VehicleType(models.TextChoices):
        BICYCLE = "bicycle", "Bicycle"
        BIKE = "bike", "Motorbike/Scooter"
        CAR = "car", "Car"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending verification"
        APPROVED = "approved", "Approved"
        SUSPENDED = "suspended", "Suspended"

    class VerificationStatus(models.TextChoices):
        DOCUMENTS_SUBMITTED = "documents_submitted", "Documents submitted"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        RESUBMISSION_REQUIRED = "resubmission_required", "Resubmission required"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"
        PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="delivery_profile", on_delete=models.CASCADE)

    # --- Personal info ---
    whatsapp_number = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True)

    # --- Address ---
    current_address = models.CharField(max_length=255, blank=True)
    permanent_address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, default="Jharkhand")
    pincode = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=100, default="India")

    # --- Vehicle ---
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices)
    vehicle_number = models.CharField(max_length=20, blank=True)
    vehicle_rc_number = models.CharField(max_length=30, blank=True)
    insurance_number = models.CharField(max_length=50, blank=True)
    insurance_expiry_date = models.DateField(null=True, blank=True)

    # --- Identity ---
    aadhaar_number = EncryptedCharField(max_length=20, blank=True, help_text="12-digit Aadhaar number")
    license_number = models.CharField(max_length=30, blank=True)
    pan_number = EncryptedCharField(max_length=10, blank=True)

    # --- Documents ---
    # Certificates (RC, insurance, license, Aadhaar, PAN) can be PDF scans —
    # FileField + extension validator. Passport photo/selfie stay ImageField.
    aadhaar_front_image = models.FileField(upload_to="delivery_documents/aadhaar/", blank=True, null=True, validators=[_doc_validator])
    aadhaar_back_image = models.FileField(upload_to="delivery_documents/aadhaar/", blank=True, null=True, validators=[_doc_validator])
    license_front_image = models.FileField(upload_to="delivery_documents/license/", blank=True, null=True, validators=[_doc_validator])
    license_back_image = models.FileField(upload_to="delivery_documents/license/", blank=True, null=True, validators=[_doc_validator])
    vehicle_rc_image = models.FileField(upload_to="delivery_documents/vehicle/", blank=True, null=True, validators=[_doc_validator])
    vehicle_insurance_image = models.FileField(upload_to="delivery_documents/vehicle/", blank=True, null=True, validators=[_doc_validator])
    pan_card_image = models.FileField(upload_to="delivery_documents/pan/", blank=True, null=True, validators=[_doc_validator])
    passport_photo = models.ImageField(upload_to="delivery_documents/photos/", blank=True, null=True)
    selfie_photo = models.ImageField(upload_to="delivery_documents/photos/", blank=True, null=True, help_text="Live selfie for identity verification")

    # Kept for backward compatibility with earlier onboarding — mirrors license_front_image/aadhaar_front_image.
    license_image = models.FileField(upload_to="delivery_documents/license/", blank=True, null=True, validators=[_doc_validator])
    aadhaar_image = models.FileField(upload_to="delivery_documents/aadhaar/", blank=True, null=True, validators=[_doc_validator])

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    verification_status = models.CharField(
        max_length=25, choices=VerificationStatus.choices, default=VerificationStatus.DOCUMENTS_SUBMITTED,
    )

    is_online = models.BooleanField(default=False, help_text="Toggled by the delivery partner to receive orders")
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_location_update = models.DateTimeField(null=True, blank=True)

    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "delivery_profiles"
        indexes = [models.Index(fields=["status", "is_online"])]

    def __str__(self):
        return f"{self.user.full_name or self.user.phone} ({self.vehicle_type})"


class DeliveryVerificationLog(models.Model):
    """Audit trail — every verification decision an admin makes on a delivery partner's documents, with notes."""

    class Action(models.TextChoices):
        MARKED_UNDER_REVIEW = "marked_under_review", "Marked under review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        RESUBMISSION_REQUESTED = "resubmission_requested", "Resubmission requested"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery_profile = models.ForeignKey(DeliveryProfile, related_name="verification_logs", on_delete=models.CASCADE)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=25, choices=Action.choices)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "delivery_verification_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.delivery_profile} — {self.action}"


class DeliveryTransaction(models.Model):
    """Earnings ledger — per-delivery payout, incentives, adjustments. Signed amount, like VendorTransaction."""

    class Type(models.TextChoices):
        DELIVERY_EARNING = "delivery_earning", "Per-delivery earning"
        INCENTIVE = "incentive", "Incentive / bonus"
        PAYOUT = "payout", "Payout to bank account"
        ADJUSTMENT = "adjustment", "Manual adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery_partner = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="delivery_transactions", on_delete=models.CASCADE
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Signed: positive=earning, negative=payout/adjustment")
    order_reference = models.CharField(max_length=50, blank=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "delivery_transactions"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["delivery_partner", "created_at"])]

    def __str__(self):
        return f"{self.delivery_partner}: {self.type} {self.amount}"


class Attendance(models.Model):
    """Simple daily check-in/check-out for delivery partners."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery_partner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="attendance", on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    check_in_time = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "delivery_attendance"
        unique_together = ("delivery_partner", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.delivery_partner} — {self.date}"

    @property
    def hours_worked(self):
        if self.check_in_time and self.check_out_time:
            return round((self.check_out_time - self.check_in_time).total_seconds() / 3600, 2)
        return None
