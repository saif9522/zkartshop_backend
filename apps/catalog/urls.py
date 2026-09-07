from rest_framework.routers import DefaultRouter

from apps.catalog.views import BrandViewSet, CategoryViewSet, ProductViewSet, ReviewViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")
router.register("products", ProductViewSet, basename="product")
router.register("reviews", ReviewViewSet, basename="review")

urlpatterns = router.urls
