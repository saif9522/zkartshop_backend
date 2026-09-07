from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.vendors.views import (
    NearbyVendorsView,
    VendorDashboardView,
    VendorOnboardView,
    VendorProfileView,
    VendorTransactionViewSet,
)

router = DefaultRouter()
router.register("transactions", VendorTransactionViewSet, basename="vendor-transaction")

urlpatterns = [
    path("onboard/", VendorOnboardView.as_view(), name="vendor-onboard"),
    path("profile/", VendorProfileView.as_view(), name="vendor-profile"),
    path("dashboard/", VendorDashboardView.as_view(), name="vendor-dashboard"),
    path("nearby/", NearbyVendorsView.as_view(), name="vendor-nearby"),
    path("", include(router.urls)),
]
