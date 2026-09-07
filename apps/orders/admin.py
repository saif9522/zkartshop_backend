from django.contrib import admin

from apps.orders.models import Coupon, Order, OrderItem, OrderStatusHistory


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product", "product_name", "unit", "price", "quantity"]


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ["from_status", "to_status", "changed_by", "changed_at"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["order_number", "customer", "vendor", "status", "payment_method", "payment_status", "grand_total", "placed_at"]
    list_filter = ["status", "payment_method", "payment_status"]
    search_fields = ["order_number", "customer__phone", "vendor__shop_name"]
    readonly_fields = ["id", "order_number", "placed_at", "updated_at"]
    inlines = [OrderItemInline, OrderStatusHistoryInline]


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ["code", "discount_type", "discount_value", "min_order_value", "used_count", "usage_limit", "is_active"]
    list_filter = ["discount_type", "is_active"]
    search_fields = ["code"]
