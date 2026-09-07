from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsCustomer, IsVendor
from apps.catalog import recommendations
from apps.catalog.filters import ProductFilter
from apps.catalog.models import Brand, Category, Product, ProductAttribute, ProductImage, ProductVariant, Review
from apps.catalog.serializers import (
    BrandSerializer,
    CategorySerializer,
    CategoryTreeSerializer,
    ProductAttributePublicSerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ProductVariantPublicSerializer,
    ProductWriteSerializer,
    ReviewSerializer,
    recalculate_product_rating,
)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """Top-level categories with subcategories nested inline — for the home screen / nav."""
        top_level = self.get_queryset().filter(parent__isnull=True).order_by("display_order", "name")
        serializer = CategoryTreeSerializer(top_level, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="home-feed")
    def home_feed(self, request):
        """
        Everything the homepage needs in one round-trip: each top-level
        category plus up to 10 of its products. Replaces what used to be
        one API call per category (slow on a store with many categories).
        """
        top_level = self.get_queryset().filter(parent__isnull=True).order_by("display_order", "name")
        base_products = (
            Product.objects.filter(is_available=True, vendor__status="approved", vendor__is_open=True)
            .select_related("vendor", "category")
            .prefetch_related("images")
        )
        feed = []
        for cat in top_level:
            products = base_products.filter(category=cat).order_by("-created_at")[:10]
            if not products:
                continue
            feed.append({
                "id": str(cat.id),
                "name": cat.name,
                "slug": cat.slug,
                "icon": request.build_absolute_uri(cat.icon.url) if cat.icon else None,
                "products": ProductListSerializer(products, many=True, context={"request": request}).data,
            })
        return Response(feed)


class BrandViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Brand.objects.filter(is_active=True)
    serializer_class = BrandSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"


class IsProductOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.vendor.owner_id == request.user.id


class ProductViewSet(viewsets.ModelViewSet):
    """
    Public browse (list/retrieve) + vendor-owned write access.
    A vendor only ever sees/edits their own products via `my-products`;
    the public list only ever shows available products from approved shops.
    """

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ["name", "description"]
    ordering_fields = ["selling_price", "created_at", "rating_avg"]
    ordering = ["-created_at"]
    lookup_field = "slug"

    OWNER_SCOPED_ACTIONS = (
        "my_products", "update", "partial_update", "destroy",
        "images", "remove_image", "attributes", "attribute_detail", "variants", "variant_detail",
    )

    def get_queryset(self):
        base = Product.objects.select_related("vendor", "category", "brand").prefetch_related(
            "images", "attributes", "variants"
        )
        if self.action in self.OWNER_SCOPED_ACTIONS:
            return base.filter(vendor__owner=self.request.user)
        return base.filter(is_available=True, vendor__status="approved", vendor__is_open=True)

    def get_serializer_class(self):
        if self.action == "list":
            return ProductListSerializer
        if self.action in ("create", "update", "partial_update"):
            return ProductWriteSerializer
        return ProductDetailSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "featured", "similar", "frequently_bought_together", "recommended_for_you"):
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsVendor()]
        return [permissions.IsAuthenticated(), IsVendor(), IsProductOwner()]

    @action(detail=False, methods=["get"], url_path="my-products")
    def my_products(self, request):
        """A vendor's full product list, including out-of-stock / inactive items."""
        self.check_permissions(request)
        if not IsVendor().has_permission(request, self):
            return Response({"detail": "Vendor access required."}, status=403)
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        serializer = ProductListSerializer(page or qs, many=True, context={"request": request})
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=False, methods=["get"])
    def featured(self, request):
        qs = self.get_queryset().filter(is_featured=True)[:20]
        serializer = ProductListSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="similar")
    def similar(self, request, slug=None):
        product = self.get_object()
        qs = recommendations.similar_products(product)
        return Response(ProductListSerializer(qs, many=True, context={"request": request}).data)

    @action(detail=True, methods=["get"], url_path="frequently-bought-together")
    def frequently_bought_together(self, request, slug=None):
        product = self.get_object()
        items = recommendations.frequently_bought_together(product)
        return Response(ProductListSerializer(items, many=True, context={"request": request}).data)

    @action(detail=False, methods=["get"], url_path="recommended-for-you")
    def recommended_for_you(self, request):
        user = request.user if request.user.is_authenticated else None
        items = recommendations.recommended_for_you(user)
        return Response(ProductListSerializer(items, many=True, context={"request": request}).data)

    @action(detail=True, methods=["get", "post"], url_path="images")
    def images(self, request, slug=None):
        """GET lists this product's images; POST adds one (multipart, `image` file + optional `is_primary`)."""
        product = self.get_object()
        if request.method == "GET":
            return Response(ProductImageSerializer(product.images.all(), many=True).data)
        if "image" not in request.FILES:
            return Response({"detail": "An `image` file is required."}, status=400)
        is_first_image = not product.images.exists()
        serializer = ProductImageSerializer(data={
            "image": request.FILES["image"],
            "is_primary": request.data.get("is_primary", False),
            "display_order": request.data.get("display_order", 0),
        })
        serializer.is_valid(raise_exception=True)
        image = serializer.save(product=product)
        if image.is_primary:
            ProductImage.objects.filter(product=product).exclude(id=image.id).update(is_primary=False)

        if is_first_image:
            from apps.core.task_utils import safe_delay
            from apps.marketing.tasks import generate_product_launch_campaign_task

            safe_delay(generate_product_launch_campaign_task, str(product.id))

        return Response(ProductImageSerializer(image).data, status=201)

    @action(detail=True, methods=["delete"], url_path="images/(?P<image_id>[^/.]+)")
    def remove_image(self, request, slug=None, image_id=None):
        product = self.get_object()
        deleted, _ = ProductImage.objects.filter(product=product, id=image_id).delete()
        if not deleted:
            return Response({"detail": "Image not found."}, status=404)
        return Response(status=204)

    @action(detail=True, methods=["get", "post"], url_path="attributes")
    def attributes(self, request, slug=None):
        product = self.get_object()
        if request.method == "GET":
            return Response(ProductAttributePublicSerializer(product.attributes.all(), many=True).data)
        serializer = ProductAttributePublicSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product)
        return Response(serializer.data, status=201)

    @action(detail=True, methods=["patch", "delete"], url_path="attributes/(?P<attribute_id>[^/.]+)")
    def attribute_detail(self, request, slug=None, attribute_id=None):
        product = self.get_object()
        attribute = get_object_or_404(ProductAttribute, product=product, id=attribute_id)
        if request.method == "DELETE":
            attribute.delete()
            return Response(status=204)
        serializer = ProductAttributePublicSerializer(attribute, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post"], url_path="variants")
    def variants(self, request, slug=None):
        product = self.get_object()
        if request.method == "GET":
            return Response(ProductVariantPublicSerializer(product.variants.all(), many=True).data)
        serializer = ProductVariantPublicSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product)
        return Response(serializer.data, status=201)

    @action(detail=True, methods=["patch", "delete"], url_path="variants/(?P<variant_id>[^/.]+)")
    def variant_detail(self, request, slug=None, variant_id=None):
        product = self.get_object()
        variant = get_object_or_404(ProductVariant, product=product, id=variant_id)
        if request.method == "DELETE":
            variant.delete()
            return Response(status=204)
        serializer = ProductVariantPublicSerializer(variant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ReviewViewSet(viewsets.ModelViewSet):
    """
    Public read (approved reviews only, filter with ?product=<id>).
    Create/update/delete restricted to the review's own author. Recomputes
    the product's rating_avg/rating_count on every write — see
    apps.catalog.serializers.recalculate_product_rating.
    """

    serializer_class = ReviewSerializer

    def get_queryset(self):
        qs = Review.objects.select_related("customer", "product")
        if self.action in ("list", "retrieve"):
            qs = qs.filter(is_approved=True)
            product_id = self.request.query_params.get("product")
            if product_id:
                qs = qs.filter(product_id=product_id)
            return qs
        # For update/destroy — only the author can touch their own review.
        if self.request.user.is_authenticated:
            return qs.filter(customer=self.request.user)
        return qs.none()

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsCustomer()]

    def perform_destroy(self, instance):
        product = instance.product
        instance.delete()
        recalculate_product_rating(product)
