from rest_framework.routers import DefaultRouter

from apps.marketing.views import BannerViewSet, OfferViewSet, SliderViewSet

router = DefaultRouter()
router.register("sliders", SliderViewSet, basename="slider")
router.register("banners", BannerViewSet, basename="banner")
router.register("offers", OfferViewSet, basename="offer")

urlpatterns = router.urls
