from rest_framework import serializers

from apps.catalog.models import Brand, Category, Product, ProductAttribute, ProductImage, ProductVariant, Review


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent", "icon", "display_order"]


class CategoryTreeSerializer(serializers.ModelSerializer):
    """Nested tree — top-level categories with their subcategories inline."""

    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "icon", "display_order", "subcategories"]

    def get_subcategories(self, obj):
        children = obj.subcategories.filter(is_active=True).order_by("display_order", "name")
        return CategorySerializer(children, many=True, context=self.context).data


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name", "slug", "logo"]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "is_primary", "display_order"]


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight — used for browse/search grids."""

    primary_image = serializers.SerializerMethodField()
    discount_percent = serializers.ReadOnlyField()
    in_stock = serializers.ReadOnlyField()
    vendor_name = serializers.CharField(source="vendor.shop_name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "unit", "mrp", "selling_price", "discount_percent",
            "primary_image", "vendor_name", "category_name", "in_stock",
            "rating_avg", "rating_count", "is_featured",
        ]

    def get_primary_image(self, obj):
        image = next((img for img in obj.images.all() if img.is_primary), None) or (
            obj.images.all()[0] if obj.images.all() else None
        )
        if image:
            request = self.context.get("request")
            url = image.image.url
            return request.build_absolute_uri(url) if request else url
        return None


class ProductAttributePublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAttribute
        fields = ["id", "name", "value"]


class ProductVariantPublicSerializer(serializers.ModelSerializer):
    in_stock = serializers.ReadOnlyField()

    class Meta:
        model = ProductVariant
        fields = ["id", "name", "sku", "mrp", "selling_price", "stock_quantity", "in_stock"]


class ProductDetailSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    attributes = ProductAttributePublicSerializer(many=True, read_only=True)
    variants = ProductVariantPublicSerializer(many=True, read_only=True)
    discount_percent = serializers.ReadOnlyField()
    in_stock = serializers.ReadOnlyField()
    vendor_name = serializers.CharField(source="vendor.shop_name", read_only=True)
    vendor_id = serializers.UUIDField(source="vendor.id", read_only=True)
    seller_business_name = serializers.CharField(source="vendor.business_name", read_only=True, default=None)
    seller_address = serializers.SerializerMethodField()
    seller_license_number = serializers.CharField(source="vendor.shop_license_number", read_only=True, default=None)
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True, default=None)
    similar_products = serializers.SerializerMethodField()
    more_from_vendor = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "description", "unit", "mrp", "selling_price",
            "discount_percent", "images", "attributes", "variants", "vendor_id", "vendor_name",
            "seller_business_name", "seller_address", "seller_license_number",
            "manufacturer_or_marketer", "country_of_origin", "shelf_life",
            "category_name", "category_slug", "brand_name", "sku", "barcode", "in_stock", "stock_quantity",
            "nutrition_info", "tags", "rating_avg", "rating_count", "similar_products",
            "more_from_vendor", "created_at",
        ]

    def get_seller_address(self, obj):
        v = obj.vendor
        parts = [v.address_line, v.city, v.state, v.pincode]
        return ", ".join(p for p in parts if p)

    def get_similar_products(self, obj):
        qs = (
            Product.objects.filter(category=obj.category, is_available=True)
            .exclude(id=obj.id)
            .select_related("vendor", "category")
            .prefetch_related("images")[:6]
        )
        return ProductListSerializer(qs, many=True, context=self.context).data

    def get_more_from_vendor(self, obj):
        qs = (
            Product.objects.filter(vendor=obj.vendor, is_available=True)
            .exclude(id=obj.id)
            .select_related("vendor", "category")
            .prefetch_related("images")[:8]
        )
        return ProductListSerializer(qs, many=True, context=self.context).data


class ProductWriteSerializer(serializers.ModelSerializer):
    """Used by vendors to create/update their own products."""

    class Meta:
        model = Product
        fields = [
            "id", "category", "brand", "name", "description", "unit", "mrp",
            "selling_price", "sku", "barcode", "stock_quantity", "is_available",
            "nutrition_info", "tags", "manufacturer_or_marketer", "country_of_origin", "shelf_life",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        mrp = attrs.get("mrp", getattr(self.instance, "mrp", None))
        selling_price = attrs.get("selling_price", getattr(self.instance, "selling_price", None))
        if mrp is not None and selling_price is not None and selling_price > mrp:
            raise serializers.ValidationError("Selling price cannot exceed MRP.")
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        if not hasattr(request.user, "vendor_profile"):
            raise serializers.ValidationError("You haven't registered a shop yet — complete vendor onboarding first.")
        validated_data["vendor"] = request.user.vendor_profile
        return super().create(validated_data)


def recalculate_product_rating(product):
    from django.db.models import Avg, Count

    agg = Review.objects.filter(product=product, is_approved=True).aggregate(avg=Avg("rating"), count=Count("id"))
    product.rating_avg = round(agg["avg"] or 0, 2)
    product.rating_count = agg["count"] or 0
    product.save(update_fields=["rating_avg", "rating_count"])


class ReviewSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)

    class Meta:
        model = Review
        fields = ["id", "product", "customer_name", "rating", "comment", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate_product(self, product):
        # Only a customer with a DELIVERED order containing this product may
        # review it — otherwise anyone could post unverified reviews.
        from apps.orders.models import Order

        user = self.context["request"].user
        has_delivered_order = Order.objects.filter(
            customer=user, status=Order.Status.DELIVERED, items__product=product
        ).exists()
        if not has_delivered_order:
            raise serializers.ValidationError("You can only review products from a delivered order.")

        if self.instance is None and Review.objects.filter(product=product, customer=user).exists():
            raise serializers.ValidationError("You've already reviewed this product.")
        return product

    def create(self, validated_data):
        validated_data["customer"] = self.context["request"].user
        review = super().create(validated_data)
        recalculate_product_rating(review.product)
        return review

    def update(self, instance, validated_data):
        review = super().update(instance, validated_data)
        recalculate_product_rating(review.product)
        return review
