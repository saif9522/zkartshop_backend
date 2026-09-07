from django.db import models
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsVendor
from apps.inventory.models import StockBatch, StockMovement, VendorWarehouse
from apps.inventory.serializers import StockBatchSerializer, StockMovementSerializer, VendorWarehouseSerializer
from apps.inventory.services import record_stock_movement


class VendorWarehouseViewSet(viewsets.ModelViewSet):
    """A vendor's own warehouses/stock locations."""

    serializer_class = VendorWarehouseSerializer
    permission_classes = [permissions.IsAuthenticated, IsVendor]

    def get_queryset(self):
        return VendorWarehouse.objects.filter(vendor__owner=self.request.user)

    def perform_create(self, serializer):
        if not hasattr(self.request.user, "vendor_profile"):
            from rest_framework.exceptions import ValidationError

            raise ValidationError("You haven't registered a shop yet — complete vendor onboarding first.")
        serializer.save(vendor=self.request.user.vendor_profile)


class StockBatchViewSet(viewsets.ModelViewSet):
    """
    A vendor's own stock batches. Creating/deleting a batch keeps the
    parent Product.stock_quantity (the fast-path total customers see) in sync.
    """

    serializer_class = StockBatchSerializer
    permission_classes = [permissions.IsAuthenticated, IsVendor]

    def get_queryset(self):
        return StockBatch.objects.filter(product__vendor__owner=self.request.user).select_related("product")

    def perform_create(self, serializer):
        batch = serializer.save()
        # Incoming stock is additive to whatever's currently sellable — units
        # already sold (decremented by checkout) must not be recomputed away.
        product = batch.product
        product.stock_quantity = models.F("stock_quantity") + batch.quantity
        product.save(update_fields=["stock_quantity"])
        product.refresh_from_db(fields=["stock_quantity"])
        record_stock_movement(
            product, StockMovement.MovementType.PURCHASE, batch.quantity,
            reference=batch.batch_number, notes="Batch received", actor=self.request.user,
        )

    def perform_update(self, serializer):
        old_quantity = serializer.instance.quantity
        batch = serializer.save()
        delta = batch.quantity - old_quantity
        if delta:
            product = batch.product
            product.stock_quantity = models.functions.Greatest(models.F("stock_quantity") + delta, 0)
            product.save(update_fields=["stock_quantity"])
            product.refresh_from_db(fields=["stock_quantity"])
            record_stock_movement(
                product, StockMovement.MovementType.ADJUSTMENT, delta,
                reference=batch.batch_number, notes="Batch quantity corrected", actor=self.request.user,
            )

    def perform_destroy(self, instance):
        product = instance.product
        quantity = instance.quantity
        batch_number = instance.batch_number
        instance.delete()
        product.stock_quantity = models.functions.Greatest(models.F("stock_quantity") - quantity, 0)
        product.save(update_fields=["stock_quantity"])
        product.refresh_from_db(fields=["stock_quantity"])
        record_stock_movement(
            product, StockMovement.MovementType.ADJUSTMENT, -quantity,
            reference=batch_number, notes="Batch removed", actor=self.request.user,
        )

    @action(detail=False, methods=["get"], url_path="expiring-soon")
    def expiring_soon(self, request):
        """Batches expiring within 3 days — the same window the daily Celery job checks."""
        cutoff = timezone.localdate() + timezone.timedelta(days=3)
        qs = self.get_queryset().filter(expiry_date__isnull=False, expiry_date__lte=cutoff, quantity__gt=0)
        return Response(StockBatchSerializer(qs, many=True).data)

    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request):
        """Products (not batches) at or below the low-stock threshold."""
        from apps.catalog.models import Product
        from apps.catalog.serializers import ProductListSerializer

        products = Product.objects.filter(
            vendor__owner=request.user, stock_quantity__lte=10, stock_quantity__gt=0, is_available=True
        )
        return Response(ProductListSerializer(products, many=True, context={"request": request}).data)


class StockMovementViewSet(viewsets.ModelViewSet):
    """
    Full stock ledger for a vendor's own products. Read is unrestricted
    (every movement type shows). Create always makes a manual ADJUSTMENT
    row (system events — sales, returns, batch changes — are logged
    automatically elsewhere, not through this endpoint). Update/delete are
    only permitted on ADJUSTMENT rows, and both correctly reverse/reapply
    the delta against Product.stock_quantity so the ledger never drifts
    from the number customers actually see.
    """

    serializer_class = StockMovementSerializer
    permission_classes = [permissions.IsAuthenticated, IsVendor]

    def get_queryset(self):
        return StockMovement.objects.filter(product__vendor__owner=self.request.user).select_related(
            "product", "created_by"
        )

    def perform_create(self, serializer):
        product = serializer.validated_data["product"]
        delta = serializer.validated_data["quantity_delta"]
        product.stock_quantity = models.functions.Greatest(models.F("stock_quantity") + delta, 0)
        product.save(update_fields=["stock_quantity"])
        product.refresh_from_db(fields=["stock_quantity"])
        serializer.save(
            movement_type=StockMovement.MovementType.ADJUSTMENT,
            resulting_stock=product.stock_quantity,
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance.movement_type != StockMovement.MovementType.ADJUSTMENT:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("Only manual adjustment entries can be edited.")
        old_delta = instance.quantity_delta
        new_delta = serializer.validated_data.get("quantity_delta", old_delta)
        diff = new_delta - old_delta
        product = instance.product
        if diff:
            product.stock_quantity = models.functions.Greatest(models.F("stock_quantity") + diff, 0)
            product.save(update_fields=["stock_quantity"])
            product.refresh_from_db(fields=["stock_quantity"])
        serializer.save(resulting_stock=product.stock_quantity)

    def perform_destroy(self, instance):
        if instance.movement_type != StockMovement.MovementType.ADJUSTMENT:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("Only manual adjustment entries can be deleted.")
        product = instance.product
        # Reverse this adjustment's effect before removing its ledger row.
        product.stock_quantity = models.functions.Greatest(models.F("stock_quantity") - instance.quantity_delta, 0)
        product.save(update_fields=["stock_quantity"])
        instance.delete()
