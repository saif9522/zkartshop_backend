from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.cart.views import CartItemAddView, CartItemDetailView, CartView, WishlistViewSet

router = DefaultRouter()
router.register("wishlist", WishlistViewSet, basename="wishlist")

urlpatterns = [
    path("", CartView.as_view(), name="cart-detail"),
    path("items/", CartItemAddView.as_view(), name="cart-item-add"),
    path("items/<uuid:item_id>/", CartItemDetailView.as_view(), name="cart-item-detail"),
    path("", include(router.urls)),
]
