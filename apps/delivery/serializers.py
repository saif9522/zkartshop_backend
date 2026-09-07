from rest_framework import serializers

from apps.core.document_access import SignedDocumentFieldsMixin
from apps.delivery.models import Attendance, DeliveryProfile, DeliveryTransaction, DeliveryVerificationLog
from apps.orders.models import Order

_PERSONAL_FIELDS = ["whatsapp_number", "date_of_birth", "gender"]
_ADDRESS_FIELDS = ["current_address", "permanent_address", "city", "state", "pincode", "country"]
_VEHICLE_FIELDS = ["vehicle_type", "vehicle_number", "vehicle_rc_number", "insurance_number", "insurance_expiry_date"]
_IDENTITY_FIELDS = ["aadhaar_number", "license_number", "pan_number"]
_DOCUMENT_FIELDS = [
    "aadhaar_front_image", "aadhaar_back_image", "license_front_image", "license_back_image",
    "vehicle_rc_image", "vehicle_insurance_image", "pan_card_image", "passport_photo", "selfie_photo",
]


class DeliveryOnboardSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryProfile
        fields = (
            ["id"] + _PERSONAL_FIELDS + _ADDRESS_FIELDS + _VEHICLE_FIELDS + _IDENTITY_FIELDS + _DOCUMENT_FIELDS
            + ["status", "verification_status"]
        )
        read_only_fields = ["id", "status", "verification_status"]

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class DeliveryProfileSerializer(SignedDocumentFieldsMixin, serializers.ModelSerializer):
    document_field_names = _DOCUMENT_FIELDS

    class Meta:
        model = DeliveryProfile
        fields = (
            ["id"] + _PERSONAL_FIELDS + _ADDRESS_FIELDS + _VEHICLE_FIELDS + _IDENTITY_FIELDS + _DOCUMENT_FIELDS
            + [
                "status", "verification_status", "is_online", "current_latitude", "current_longitude",
                "last_location_update", "rating_avg", "rating_count", "created_at", "last_login_at",
            ]
        )
        read_only_fields = [
            "id", "status", "verification_status", "current_latitude", "current_longitude",
            "last_location_update", "rating_avg", "rating_count", "created_at", "last_login_at",
        ]


class DeliveryVerificationLogSerializer(serializers.ModelSerializer):
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name", read_only=True, default=None)

    class Meta:
        model = DeliveryVerificationLog
        fields = ["id", "action", "notes", "reviewed_by_name", "created_at"]
        read_only_fields = fields


class LocationUpdateSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)


class OTPSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6)


class AvailableOrderSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.shop_name", read_only=True)
    vendor_address = serializers.CharField(source="vendor.address_line", read_only=True)
    vendor_phone = serializers.CharField(source="vendor.owner.phone", read_only=True)
    vendor_latitude = serializers.DecimalField(source="vendor.latitude", max_digits=9, decimal_places=6, read_only=True)
    vendor_longitude = serializers.DecimalField(source="vendor.longitude", max_digits=9, decimal_places=6, read_only=True)
    item_count = serializers.IntegerField(source="items.count", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "vendor_name", "vendor_address", "vendor_phone", "vendor_latitude",
            "vendor_longitude", "item_count", "grand_total", "placed_at",
        ]


class MyDeliveryOrderSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.shop_name", read_only=True)
    vendor_address = serializers.CharField(source="vendor.address_line", read_only=True)
    vendor_phone = serializers.CharField(source="vendor.owner.phone", read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    delivery_address_text = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(source="items.count", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "status", "vendor_name", "vendor_address", "vendor_phone",
            "customer_name", "customer_phone", "delivery_address_text", "item_count", "grand_total",
            "payment_method", "payment_status", "placed_at",
        ]

    def get_delivery_address_text(self, obj):
        addr = obj.delivery_address
        return f"{addr.address_line}, {addr.city} - {addr.pincode}"


class DeliveryTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryTransaction
        fields = ["id", "type", "amount", "order_reference", "description", "created_at"]
        read_only_fields = fields


class AttendanceSerializer(serializers.ModelSerializer):
    hours_worked = serializers.ReadOnlyField()

    class Meta:
        model = Attendance
        fields = ["id", "date", "check_in_time", "check_out_time", "hours_worked"]
        read_only_fields = fields
