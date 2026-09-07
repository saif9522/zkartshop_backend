import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models

from apps.core.encrypted_fields import EncryptedCharField

DOCUMENT_EXTENSIONS = ["png", "jpg", "jpeg", "webp", "pdf"]
_doc_validator = FileExtensionValidator(allowed_extensions=DOCUMENT_EXTENSIONS)


class ShopCategory(models.TextChoices):
    GROCERY = "grocery", "Grocery"
    FRUITS_VEGETABLES = "fruits_vegetables", "Fruits & vegetables"
    MEDICAL = "medical", "Medical"
    BAKERY = "bakery", "Bakery"
    MEAT = "meat", "Meat"
    ELECTRONICS = "electronics", "Electronics"
    CLOTHING = "clothing", "Clothing"


class Vendor(models.Model):
    """
    One row per shop. A User with role='vendor' owns exactly one Vendor;
    the platform can later support multiple staff per shop via a separate
    VendorStaff model if needed.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        SUSPENDED = "suspended", "Suspended"

    class VerificationStatus(models.TextChoices):
        DOCUMENTS_SUBMITTED = "documents_submitted", "Documents submitted"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        RESUBMISSION_REQUIRED = "resubmission_required", "Resubmission required"

    class BusinessType(models.TextChoices):
        SOLE_PROPRIETORSHIP = "sole_proprietorship", "Sole proprietorship"
        PARTNERSHIP = "partnership", "Partnership"
        PRIVATE_LIMITED = "private_limited", "Private limited company"
        LLP = "llp", "LLP"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="vendor_profile", on_delete=models.CASCADE)

    # --- Basic info ---
    shop_name = models.CharField(max_length=150)
    business_name = models.CharField(max_length=150, blank=True, help_text="Legal/registered business name, if different from the shop name")
    whatsapp_number = models.CharField(max_length=20, blank=True)
    category = models.CharField(max_length=30, choices=ShopCategory.choices)

    # --- Business info ---
    gst_number = models.CharField(max_length=15, blank=True)
    pan_number = EncryptedCharField(max_length=10, blank=True)
    business_registration_number = models.CharField(max_length=50, blank=True)
    shop_license_number = models.CharField(max_length=50, blank=True)
    fssai_license_number = models.CharField(max_length=20, blank=True, help_text="Required for food businesses")
    business_type = models.CharField(max_length=30, choices=BusinessType.choices, blank=True)
    years_in_business = models.PositiveSmallIntegerField(null=True, blank=True)

    # --- Bank details (for payouts) ---
    bank_account_holder_name = models.CharField(max_length=150, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_number = EncryptedCharField(max_length=30, blank=True)
    bank_ifsc_code = models.CharField(max_length=11, blank=True)
    upi_id = models.CharField(max_length=100, blank=True)

    # --- Documents ---
    # Certificates/licenses can legitimately be a PDF scan, not just a photo —
    # FileField + extension validator accepts either. Photos (shop/owner) stay
    # ImageField since a selfie/photo can't sensibly be a PDF.
    gst_certificate = models.FileField(upload_to="vendor_documents/gst/", blank=True, null=True, validators=[_doc_validator])
    pan_card = models.FileField(upload_to="vendor_documents/pan/", blank=True, null=True, validators=[_doc_validator])
    aadhaar_card = models.FileField(upload_to="vendor_documents/aadhaar/", blank=True, null=True, validators=[_doc_validator])
    shop_document = models.FileField(
        upload_to="vendor_documents/shop/", blank=True, null=True, validators=[_doc_validator],
        help_text="Shop license / trade registration proof",
    )
    business_registration_document = models.FileField(upload_to="vendor_documents/business_reg/", blank=True, null=True, validators=[_doc_validator])
    fssai_license_document = models.FileField(upload_to="vendor_documents/fssai/", blank=True, null=True, validators=[_doc_validator])
    cancelled_cheque = models.FileField(upload_to="vendor_documents/bank/", blank=True, null=True, validators=[_doc_validator], help_text="Cancelled cheque or other bank proof")
    shop_front_photo = models.ImageField(upload_to="vendor_documents/shop_photos/", blank=True, null=True)
    shop_interior_photo = models.ImageField(upload_to="vendor_documents/shop_photos/", blank=True, null=True)
    owner_photo = models.ImageField(upload_to="vendor_documents/owner/", blank=True, null=True)

    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    verification_status = models.CharField(
        max_length=25, choices=VerificationStatus.choices, default=VerificationStatus.DOCUMENTS_SUBMITTED,
    )

    # --- Address ---
    address_line = models.CharField(max_length=255)
    city = models.CharField(max_length=100, default="Garhwa")
    city_ref = models.ForeignKey(
        "superadmin.City", related_name="vendors", null=True, blank=True, on_delete=models.SET_NULL,
        help_text="Optional link to the managed City registry, for city-level delivery pricing overrides",
    )
    state = models.CharField(max_length=100, default="Jharkhand")
    pincode = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=100, default="India")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    is_open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "vendors"
        indexes = [models.Index(fields=["category", "status"])]

    def __str__(self):
        return self.shop_name


class VendorVerificationLog(models.Model):
    """Audit trail — every verification decision an admin makes on a vendor's documents, with notes."""

    class Action(models.TextChoices):
        MARKED_UNDER_REVIEW = "marked_under_review", "Marked under review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        RESUBMISSION_REQUESTED = "resubmission_requested", "Resubmission requested"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, related_name="verification_logs", on_delete=models.CASCADE)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=25, choices=Action.choices)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vendor_verification_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.vendor.shop_name} — {self.action}"


class VendorTransaction(models.Model):
    """
    Ledger of everything that moves a vendor's payable balance — order
    settlements (credit, net of commission), platform commission (debit),
    manual adjustments, and payouts (debit). Balance = sum of all entries.

    TODO (Phase 7 — Orders): once an order is delivered, auto-create a
    CREDIT entry here for (order total - commission_percent) and a
    COMMISSION debit entry, via a Celery task triggered on order completion.
    """

    class Type(models.TextChoices):
        CREDIT = "credit", "Credit (order settlement)"
        COMMISSION = "commission", "Platform commission"
        PAYOUT = "payout", "Payout to vendor bank account"
        ADJUSTMENT = "adjustment", "Manual adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, related_name="transactions", on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=Type.choices)
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Signed: positive for credits, negative for commission/payout/adjustment-debits",
    )
    order_reference = models.CharField(max_length=50, blank=True, help_text="Order number, once orders exist")
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vendor_transactions"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["vendor", "type", "created_at"])]

    def __str__(self):
        return f"{self.vendor.shop_name}: {self.type} {self.amount}"
