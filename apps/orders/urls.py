from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.orders.views import (
    CheckoutView,
    CouponValidateView,
    DeliveryEstimateView,
    OrderViewSet,
    PaymentMethodsView,
    PaymentVerifyView,
    VendorOrderViewSet,
)

router = DefaultRouter()
router.register("vendor", VendorOrderViewSet, basename="vendor-order")
router.register("", OrderViewSet, basename="order")

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("delivery-estimate/", DeliveryEstimateView.as_view(), name="delivery-estimate"),
    path("payments/verify/", PaymentVerifyView.as_view(), name="payment-verify"),
    path("payment-methods/", PaymentMethodsView.as_view(), name="payment-methods"),
    path("coupons/validate/", CouponValidateView.as_view(), name="coupon-validate"),
    path("", include(router.urls)),
]
