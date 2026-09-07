import django_filters

from apps.catalog.models import Product


class ProductFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name="category__slug")
    brand = django_filters.CharFilter(field_name="brand__slug")
    vendor = django_filters.UUIDFilter(field_name="vendor_id")
    min_price = django_filters.NumberFilter(field_name="selling_price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="selling_price", lookup_expr="lte")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")
    min_discount = django_filters.NumberFilter(method="filter_min_discount")

    class Meta:
        model = Product
        fields = ["category", "brand", "vendor", "min_price", "max_price", "in_stock", "min_discount", "is_featured"]

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(is_available=True, stock_quantity__gt=0)
        return queryset

    def filter_min_discount(self, queryset, name, value):
        # discount_percent is a Python property, not a DB column — filter in-memory.
        ids = [p.id for p in queryset if p.discount_percent >= value]
        return queryset.filter(id__in=ids)
