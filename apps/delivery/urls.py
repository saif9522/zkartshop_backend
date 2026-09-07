from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.delivery.views import (
    AssignOrderView,
    AttendanceViewSet,
    AvailableOrdersView,
    CheckInView,
    CheckOutView,
    ConfirmDeliveryView,
    ConfirmPickupView,
    DeliveryDashboardView,
    DeliveryOnboardView,
    DeliveryProfileView,
    DeliveryTransactionViewSet,
    GoOnlineView,
    LocationUpdateView,
    MarkNearbyView,
    MyDeliveryOrdersView,
    RouteView,
    StartDeliveryView,
)

router = DefaultRouter()
router.register("transactions", DeliveryTransactionViewSet, basename="delivery-transaction")
router.register("attendance", AttendanceViewSet, basename="delivery-attendance")

urlpatterns = [
    path("onboard/", DeliveryOnboardView.as_view(), name="delivery-onboard"),
    path("profile/", DeliveryProfileView.as_view(), name="delivery-profile"),
    path("go-online/", GoOnlineView.as_view(), name="delivery-go-online"),
    path("location/", LocationUpdateView.as_view(), name="delivery-location"),
    path("dashboard/", DeliveryDashboardView.as_view(), name="delivery-dashboard"),
    path("orders/available/", AvailableOrdersView.as_view(), name="delivery-available-orders"),
    path("orders/mine/", MyDeliveryOrdersView.as_view(), name="delivery-my-orders"),
    path("orders/<uuid:order_id>/assign/", AssignOrderView.as_view(), name="delivery-assign"),
    path("orders/<uuid:order_id>/confirm-pickup/", ConfirmPickupView.as_view(), name="delivery-confirm-pickup"),
    path("orders/<uuid:order_id>/start-delivery/", StartDeliveryView.as_view(), name="delivery-start"),
    path("orders/<uuid:order_id>/mark-nearby/", MarkNearbyView.as_view(), name="delivery-nearby"),
    path("orders/<uuid:order_id>/confirm-delivery/", ConfirmDeliveryView.as_view(), name="delivery-confirm"),
    path("orders/<uuid:order_id>/route/", RouteView.as_view(), name="delivery-route"),
    path("attendance/check-in/", CheckInView.as_view(), name="attendance-check-in"),
    path("attendance/check-out/", CheckOutView.as_view(), name="attendance-check-out"),
    path("", include(router.urls)),
]
