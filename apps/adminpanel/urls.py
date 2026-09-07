from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.adminpanel.views import (
    AdminBannerViewSet,
    AdminBlogPostViewSet,
    AdminBroadcastNotificationView,
    AdminBrandViewSet,
    AdminCategoryViewSet,
    AdminContactMessageViewSet,
    AdminCouponViewSet,
    AdminCampaignAnalyticsView,
    AdminDashboardView,
    AdminDeliveryPartnerViewSet,
    AdminExpiringStockView,
    AdminFAQViewSet,
    AdminFooterLinkViewSet,
    AdminLowStockView,
    AdminMediaAssetViewSet,
    AdminCampaignViewSet,
    AdminWalletTransactionViewSet,
    AdminOfferViewSet,
    AdminOrderViewSet,
    AdminPageViewSet,
    AdminExtraChargeViewSet,
    AdminPaymentMethodConfigViewSet,
    AdminProductViewSet,
    AdminReviewViewSet,
    AdminSliderViewSet,
    AdminUserViewSet,
    AdminVendorViewSet,
)

router = DefaultRouter()
router.register("users", AdminUserViewSet, basename="admin-user")
router.register("vendors", AdminVendorViewSet, basename="admin-vendor")
router.register("delivery-partners", AdminDeliveryPartnerViewSet, basename="admin-delivery-partner")
router.register("orders", AdminOrderViewSet, basename="admin-order")
router.register("coupons", AdminCouponViewSet, basename="admin-coupon")
router.register("categories", AdminCategoryViewSet, basename="admin-category")
router.register("brands", AdminBrandViewSet, basename="admin-brand")
router.register("reviews", AdminReviewViewSet, basename="admin-review")
router.register("sliders", AdminSliderViewSet, basename="admin-slider")
router.register("banners", AdminBannerViewSet, basename="admin-banner")
router.register("offers", AdminOfferViewSet, basename="admin-offer")
router.register("faqs", AdminFAQViewSet, basename="admin-faq")
router.register("pages", AdminPageViewSet, basename="admin-page")
router.register("blog", AdminBlogPostViewSet, basename="admin-blogpost")
router.register("footer-links", AdminFooterLinkViewSet, basename="admin-footerlink")
router.register("contact-messages", AdminContactMessageViewSet, basename="admin-contactmessage")
router.register("payment-methods", AdminPaymentMethodConfigViewSet, basename="admin-payment-method")
router.register("extra-charges", AdminExtraChargeViewSet, basename="admin-extra-charge")
router.register("media-library", AdminMediaAssetViewSet, basename="admin-media-asset")
router.register("wallet-transactions", AdminWalletTransactionViewSet, basename="admin-wallet-transaction")
router.register("campaigns", AdminCampaignViewSet, basename="admin-campaign")
router.register("products", AdminProductViewSet, basename="admin-product")

urlpatterns = [
    path("dashboard/", AdminDashboardView.as_view(), name="admin-dashboard"),
    path("campaigns/analytics/", AdminCampaignAnalyticsView.as_view(), name="admin-campaign-analytics"),
    path("inventory/low-stock/", AdminLowStockView.as_view(), name="admin-low-stock"),
    path("inventory/expiring-soon/", AdminExpiringStockView.as_view(), name="admin-expiring-soon"),
    path("notifications/broadcast/", AdminBroadcastNotificationView.as_view(), name="admin-broadcast"),
    path("", include(router.urls)),
]
