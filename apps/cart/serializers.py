from django.conf import settings
from rest_framework import serializers

from apps.cart.models import Cart, CartItem, WishlistItem
from apps.catalog.models import Product
from apps.catalog.serializers import ProductListSerializer


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = CartItem
        fields = ["id", "product", "quantity", "subtotal"]


class AddToCartSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate_product_id(self, value):
        try:
            product = Product.objects.get(id=value, is_available=True)
        except Product.DoesNotExist as exc:
            raise serializers.ValidationError("Product not found or unavailable.") from exc
        self.product = product
        return value

    def validate(self, attrs):
        # Must check (already-in-cart + new) against stock, not just the new
        # quantity — otherwise adding to an existing line item can push the
        # cart's total past what's actually in stock.
        existing_qty = 0
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            existing_qty = (
                CartItem.objects.filter(cart__user=request.user, product_id=attrs["product_id"])
                .values_list("quantity", flat=True)
                .first()
                or 0
            )
        if existing_qty + attrs["quantity"] > self.product.stock_quantity:
            remaining = max(self.product.stock_quantity - existing_qty, 0)
            raise serializers.ValidationError(f"Only {remaining} more of this item can be added (limited stock).")
        return attrs


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.ReadOnlyField()
    item_count = serializers.ReadOnlyField()
    delivery_charge = serializers.SerializerMethodField()
    grand_total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "items", "coupon_code", "subtotal", "item_count", "delivery_charge", "grand_total"]

    def get_delivery_charge(self, obj):
        from apps.superadmin.models import PlatformSettings

        platform = PlatformSettings.load()
        if obj.subtotal >= platform.default_free_delivery_threshold:
            return 0
        return platform.default_delivery_charge if obj.items.exists() else 0

    def get_grand_total(self, obj):
        return obj.subtotal + self.get_delivery_charge(obj)


class WishlistItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    product_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = WishlistItem
        fields = ["id", "product", "product_id", "added_at"]

    def validate_product_id(self, value):
        if not Product.objects.filter(id=value).exists():
            raise serializers.ValidationError("Product not found.")
        return value

    def create(self, validated_data):
        product_id = validated_data.pop("product_id")
        wishlist_item, _ = WishlistItem.objects.get_or_create(
            user=self.context["request"].user, product_id=product_id
        )
        return wishlist_item
