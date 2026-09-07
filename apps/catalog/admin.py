from django.contrib import admin

from apps.catalog.models import Brand, Category, Product, ProductImage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "parent", "display_order", "is_active"]
    list_filter = ["is_active", "parent"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "vendor", "category", "selling_price", "mrp", "stock_quantity", "is_available"]
    list_filter = ["category", "is_available", "is_featured", "vendor"]
    search_fields = ["name", "sku", "barcode"]
    inlines = [ProductImageInline]
    readonly_fields = ["rating_avg", "rating_count", "created_at", "updated_at"]
