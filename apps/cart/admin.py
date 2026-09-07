from django.contrib import admin

from apps.cart.models import Cart, CartItem, WishlistItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["user", "item_count", "subtotal", "updated_at"]
    search_fields = ["user__phone"]
    inlines = [CartItemInline]


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ["user", "product", "added_at"]
    search_fields = ["user__phone", "product__name"]
