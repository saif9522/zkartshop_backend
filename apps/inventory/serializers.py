from rest_framework import serializers

from apps.catalog.models import Product
from apps.inventory.models import StockBatch, StockMovement, VendorWarehouse


class VendorWarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorWarehouse
        fields = ["id", "name", "address_line", "is_default", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class StockBatchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True, default=None)
    is_expired = serializers.ReadOnlyField()

    class Meta:
        model = StockBatch
        fields = [
            "id", "product", "product_name", "warehouse", "warehouse_name", "batch_number", "quantity",
            "purchase_price", "supplier_name", "expiry_date", "received_date",
            "is_expired", "created_at",
        ]
        read_only_fields = ["id", "received_date", "created_at"]

    def validate_product(self, value):
        request = self.context["request"]
        if value.vendor.owner_id != request.user.id:
            raise serializers.ValidationError("You can only add stock for your own products.")
        return value

    def validate_warehouse(self, value):
        if value is None:
            return value
        request = self.context["request"]
        if value.vendor.owner_id != request.user.id:
            raise serializers.ValidationError("That warehouse doesn't belong to you.")
        return value


class StockMovementSerializer(serializers.ModelSerializer):
    """
    Full ledger read, but movement_type/resulting_stock/reference/created_by
    are always system-set — the only thing a vendor can directly create or
    edit through this serializer is a manual ADJUSTMENT's quantity_delta/notes.
    """

    product_name = serializers.CharField(source="product.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)

    class Meta:
        model = StockMovement
        fields = [
            "id", "product", "product_name", "movement_type", "quantity_delta",
            "resulting_stock", "reference", "notes", "created_by_name", "created_at",
        ]
        read_only_fields = ["id", "movement_type", "resulting_stock", "reference", "created_at"]

    def validate_product(self, value):
        request = self.context["request"]
        if value.vendor.owner_id != request.user.id:
            raise serializers.ValidationError("You can only adjust stock for your own products.")
        return value
