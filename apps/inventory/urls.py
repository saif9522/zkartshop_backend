from rest_framework.routers import DefaultRouter

from apps.inventory.views import StockBatchViewSet, StockMovementViewSet, VendorWarehouseViewSet

router = DefaultRouter()
router.register("warehouses", VendorWarehouseViewSet, basename="vendor-warehouse")
router.register("stock-batches", StockBatchViewSet, basename="stock-batch")
router.register("stock-movements", StockMovementViewSet, basename="stock-movement")

urlpatterns = router.urls
