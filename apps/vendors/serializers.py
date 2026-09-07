from rest_framework import serializers

from apps.core.document_access import SignedDocumentFieldsMixin
from apps.vendors.models import Vendor, VendorTransaction, VendorVerificationLog

_DOCUMENT_FIELDS = [
    "gst_certificate", "pan_card", "aadhaar_card", "shop_document", "business_registration_document",
    "fssai_license_document", "cancelled_cheque", "shop_front_photo", "shop_interior_photo", "owner_photo",
]
_BUSINESS_FIELDS = [
    "gst_number", "pan_number", "business_registration_number", "shop_license_number",
    "fssai_license_number", "business_type", "years_in_business",
]
_BANK_FIELDS = ["bank_account_holder_name", "bank_name", "bank_account_number", "bank_ifsc_code", "upi_id"]
_ADDRESS_FIELDS = ["address_line", "city", "state", "pincode", "country", "latitude", "longitude"]


class VendorOnboardSerializer(serializers.ModelSerializer):
    """Used once by a vendor-role user to create their shop profile — the full KYC form."""

    class Meta:
        model = Vendor
        fields = (
            ["id", "shop_name", "business_name", "whatsapp_number", "category"]
            + _BUSINESS_FIELDS + _ADDRESS_FIELDS + _BANK_FIELDS + _DOCUMENT_FIELDS
            + ["status", "verification_status"]
        )
        read_only_fields = ["id", "status", "verification_status"]

    def create(self, validated_data):
        validated_data["owner"] = self.context["request"].user
        return super().create(validated_data)


class VendorProfileSerializer(SignedDocumentFieldsMixin, serializers.ModelSerializer):
    """Used by the vendor to view/update their own shop after onboarding."""

    document_field_names = _DOCUMENT_FIELDS

    class Meta:
        model = Vendor
        fields = (
            ["id", "shop_name", "business_name", "whatsapp_number", "category"]
            + _BUSINESS_FIELDS + _ADDRESS_FIELDS + _BANK_FIELDS + _DOCUMENT_FIELDS
            + ["commission_percent", "status", "verification_status", "is_open", "created_at", "last_login_at"]
        )
        read_only_fields = ["id", "status", "verification_status", "commission_percent", "created_at", "last_login_at"]


class VendorNearbySerializer(serializers.ModelSerializer):
    """Public, read-only — used by the customer app's nearby-stores browse."""

    distance_km = serializers.FloatField(read_only=True)

    class Meta:
        model = Vendor
        fields = [
            "id", "shop_name", "category", "address_line", "city", "latitude", "longitude",
            "is_open", "distance_km",
        ]


class VendorTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorTransaction
        fields = ["id", "type", "amount", "order_reference", "description", "created_at"]
        read_only_fields = fields


class VendorVerificationLogSerializer(serializers.ModelSerializer):
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name", read_only=True, default=None)

    class Meta:
        model = VendorVerificationLog
        fields = ["id", "action", "notes", "reviewed_by_name", "created_at"]
        read_only_fields = fields
