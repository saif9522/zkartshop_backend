from rest_framework import serializers

from apps.core.models import AuditLog
from apps.superadmin.models import City, PlatformSettings, StaffPermission, Warehouse


class CitySerializer(serializers.ModelSerializer):
    vendor_count = serializers.IntegerField(source="vendors.count", read_only=True)

    class Meta:
        model = City
        fields = [
            "id", "name", "state", "delivery_charge", "free_delivery_threshold",
            "is_active", "vendor_count", "created_at",
        ]
        read_only_fields = ["id", "vendor_count", "created_at"]


class WarehouseSerializer(serializers.ModelSerializer):
    city_name = serializers.CharField(source="city.name", read_only=True)

    class Meta:
        model = Warehouse
        fields = ["id", "name", "city", "city_name", "address_line", "latitude", "longitude", "is_active", "created_at"]
        read_only_fields = ["id", "city_name", "created_at"]


class PlatformSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformSettings
        fields = [
            "default_commission_percent", "default_delivery_charge",
            "default_free_delivery_threshold", "order_accept_timeout_minutes",
            "maintenance_mode", "updated_at",
        ]
        read_only_fields = ["updated_at"]


class StaffPermissionSerializer(serializers.ModelSerializer):
    user_phone = serializers.CharField(source="user.phone", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = StaffPermission
        fields = [
            "id", "user", "user_phone", "user_name", "department", "can_manage_vendors",
            "can_manage_delivery_partners", "can_manage_orders", "can_manage_coupons",
            "can_manage_categories", "can_manage_users", "can_view_reports", "updated_at",
        ]
        read_only_fields = ["id", "user_phone", "user_name", "updated_at"]

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        # A non-custom department wins: its preset overwrites the section flags.
        if "department" in validated_data:
            instance.apply_department_preset()
            instance.save()
        return instance


class CreateAdminSerializer(serializers.Serializer):
    """Super admin creates a new admin-role staff account with an initial permission set."""

    phone = serializers.CharField()
    full_name = serializers.CharField()
    password = serializers.CharField(min_length=8, write_only=True)
    department = serializers.ChoiceField(
        choices=StaffPermission.Department.choices, default=StaffPermission.Department.CUSTOM,
    )
    can_manage_vendors = serializers.BooleanField(default=False)
    can_manage_delivery_partners = serializers.BooleanField(default=False)
    can_manage_orders = serializers.BooleanField(default=False)
    can_manage_coupons = serializers.BooleanField(default=False)
    can_manage_categories = serializers.BooleanField(default=False)
    can_manage_users = serializers.BooleanField(default=False)
    can_view_reports = serializers.BooleanField(default=True)


class AuditLogSerializer(serializers.ModelSerializer):
    user_phone = serializers.CharField(source="user.phone", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ["id", "user", "user_phone", "method", "path", "status_code", "ip_address", "created_at"]
        read_only_fields = fields
