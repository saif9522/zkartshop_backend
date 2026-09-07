from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsCustomer
from apps.cart.models import Cart, CartItem, WishlistItem
from apps.cart.serializers import (
    AddToCartSerializer,
    CartSerializer,
    UpdateCartItemSerializer,
    WishlistItemSerializer,
)


def _get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


class CartView(APIView):
    """GET the current cart. DELETE clears it."""

    permission_classes = [IsCustomer]

    def get(self, request):
        cart = _get_or_create_cart(request.user)
        return Response(CartSerializer(cart).data)

    def delete(self, request):
        cart = _get_or_create_cart(request.user)
        cart.items.all().delete()
        return Response(CartSerializer(cart).data)


class CartItemAddView(APIView):
    """Add a product to the cart, or increase quantity if it's already there."""

    permission_classes = [IsCustomer]

    def post(self, request):
        serializer = AddToCartSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        cart = _get_or_create_cart(request.user)

        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product_id=serializer.validated_data["product_id"],
            defaults={"quantity": serializer.validated_data["quantity"]},
        )
        if not created:
            item.quantity += serializer.validated_data["quantity"]
            item.save(update_fields=["quantity"])

        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)


class CartItemDetailView(APIView):
    """PATCH to change quantity, DELETE to remove the line item."""

    permission_classes = [IsCustomer]

    def get_item(self, request, item_id):
        return CartItem.objects.select_related("cart").get(id=item_id, cart__user=request.user)

    def patch(self, request, item_id):
        try:
            item = self.get_item(request, item_id)
        except CartItem.DoesNotExist:
            return Response({"detail": "Cart item not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data["quantity"] > item.product.stock_quantity:
            return Response(
                {"detail": f"Only {item.product.stock_quantity} left in stock."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item.quantity = serializer.validated_data["quantity"]
        item.save(update_fields=["quantity"])
        return Response(CartSerializer(item.cart).data)

    def delete(self, request, item_id):
        try:
            item = self.get_item(request, item_id)
        except CartItem.DoesNotExist:
            return Response({"detail": "Cart item not found."}, status=status.HTTP_404_NOT_FOUND)
        cart = item.cart
        item.delete()
        return Response(CartSerializer(cart).data)


class WishlistViewSet(viewsets.ModelViewSet):
    serializer_class = WishlistItemSerializer
    permission_classes = [IsCustomer]
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        return WishlistItem.objects.filter(user=self.request.user).select_related("product")
