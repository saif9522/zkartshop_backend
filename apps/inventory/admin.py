from django.contrib import admin

from apps.inventory.models import StockBatch


@admin.register(StockBatch)
class StockBatchAdmin(admin.ModelAdmin):
    list_display = ["product", "batch_number", "quantity", "purchase_price", "expiry_date", "supplier_name"]
    list_filter = ["expiry_date"]
    search_fields = ["product__name", "batch_number", "supplier_name"]
