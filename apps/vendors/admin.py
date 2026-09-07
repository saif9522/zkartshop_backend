from django.contrib import admin

from apps.vendors.models import Vendor, VendorTransaction


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ["shop_name", "owner", "category", "status", "is_open", "city"]
    list_filter = ["category", "status", "is_open", "city"]
    search_fields = ["shop_name", "owner__phone", "gst_number"]


@admin.register(VendorTransaction)
class VendorTransactionAdmin(admin.ModelAdmin):
    list_display = ["vendor", "type", "amount", "order_reference", "created_at"]
    list_filter = ["type"]
    search_fields = ["vendor__shop_name", "order_reference"]
    readonly_fields = ["created_at"]
