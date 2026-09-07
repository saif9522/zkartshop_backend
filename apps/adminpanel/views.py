import csv
import io

from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import filters, mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, User
from apps.accounts.permissions import IsAdmin
from apps.superadmin.permissions import (
    CanManageCategories,
    CanManageCoupons,
    CanManageDeliveryPartners,
    CanManageUsers,
    CanManageVendors,
)
from apps.adminpanel.serializers import (
    AdminBannerSerializer,
    AdminBlogPostSerializer,
    AdminBrandSerializer,
    AdminCampaignSerializer,
    AdminCategorySerializer,
    AdminContactMessageSerializer,
    AdminCouponSerializer,
    AdminCreateVendorSerializer,
    AdminDeliveryProfileSerializer,
    AdminFAQSerializer,
    AdminFooterLinkSerializer,
    AdminMediaAssetSerializer,
    AdminOfferSerializer,
    AdminPageSerializer,
    AdminExtraChargeSerializer,
    AdminPaymentMethodConfigSerializer,
    AdminProductAttributeSerializer,
    AdminProductImageSerializer,
    AdminProductSerializer,
    AdminProductVariantSerializer,
    AdminReviewSerializer,
    AdminSliderSerializer,
    AdminUserSerializer,
    AdminVendorCommissionSerializer,
    AdminVendorSerializer,
    AdminWalletTransactionSerializer,
    BroadcastNotificationSerializer,
    CampaignExternalContactSerializer,
    CampaignRecipientSerializer,
    RejectSerializer,
    SimpleCustomerSerializer,
)
from apps.catalog.models import Brand, Category, Product, ProductAttribute, ProductImage, ProductVariant, Review
from apps.catalog.serializers import recalculate_product_rating
from apps.cms.models import BlogPost, ContactMessage, FAQ, FooterLink, MediaAsset, Page
from apps.marketing.models import Banner, Campaign, CampaignExternalContact, CampaignRecipient, Offer, Slider
from apps.orders.models import Coupon, ExtraCharge, PaymentMethodConfig
from apps.wallet.models import WalletTransaction
from apps.delivery.models import DeliveryProfile, DeliveryVerificationLog
from apps.delivery.serializers import DeliveryVerificationLogSerializer
from apps.inventory.models import StockBatch
from apps.orders.models import Order
from apps.orders.serializers import OrderDetailSerializer, OrderListSerializer
from apps.vendors.models import Vendor, VendorVerificationLog
from apps.vendors.serializers import VendorVerificationLogSerializer


class AdminUserViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
    mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    serializer_class = AdminUserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["phone", "email", "full_name"]

    def get_queryset(self):
        qs = User.objects.all().order_by("-date_joined")
        role = self.request.query_params.get("role")
        return qs.filter(role=role) if role else qs

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated(), IsAdmin()]
        return [permissions.IsAuthenticated(), CanManageUsers()]

    def perform_destroy(self, instance):
        from django.db.models import ProtectedError

        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError(
                "This user has order history and can't be deleted — deactivate the account instead."
            )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(AdminUserSerializer(user).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        return Response(AdminUserSerializer(user).data)


class AdminVendorViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    serializer_class = AdminVendorSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["shop_name", "owner__phone", "gst_number"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated(), IsAdmin()]
        return [permissions.IsAuthenticated(), CanManageVendors()]

    def get_queryset(self):
        qs = Vendor.objects.select_related("owner").annotate(_product_count=Count("products"))
        status_filter = self.request.query_params.get("status")
        return qs.filter(status=status_filter) if status_filter else qs

    def create(self, request, *args, **kwargs):
        """
        Admin/super-admin adds a vendor directly — creates the owner login
        and the (already-approved) shop in one step. Separate from the
        self-serve apply flow at /api/v1/vendors/onboard/, which any
        vendor-role user can use themselves; that one still lands as
        'pending' for staff to approve/suspend below.
        """
        serializer = AdminCreateVendorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if User.objects.filter(phone=data["phone"]).exists():
            return Response({"detail": "A user with this phone already exists."}, status=400)

        owner = User.objects.create_user(
            phone=data["phone"], password=data.pop("password"), full_name=data["full_name"],
            role=Role.VENDOR, is_phone_verified=True,
        )
        vendor = Vendor.objects.create(
            owner=owner,
            shop_name=data["shop_name"],
            category=data["category"],
            gst_number=data.get("gst_number", ""),
            address_line=data["address_line"],
            city=data["city"],
            latitude=data["latitude"],
            longitude=data["longitude"],
            status=Vendor.Status.APPROVED,
        )
        return Response(AdminVendorSerializer(vendor).data, status=201)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        vendor = self.get_object()
        vendor.status = Vendor.Status.APPROVED
        vendor.verification_status = Vendor.VerificationStatus.APPROVED
        vendor.save(update_fields=["status", "verification_status"])
        VendorVerificationLog.objects.create(
            vendor=vendor, reviewed_by=request.user, action=VendorVerificationLog.Action.APPROVED,
            notes=request.data.get("notes", ""),
        )
        return Response(AdminVendorSerializer(vendor).data)

    @action(detail=True, methods=["post"], url_path="mark-under-review")
    def mark_under_review(self, request, pk=None):
        vendor = self.get_object()
        if vendor.verification_status not in (Vendor.VerificationStatus.DOCUMENTS_SUBMITTED, Vendor.VerificationStatus.RESUBMISSION_REQUIRED):
            return Response({"detail": f"Can't move from '{vendor.verification_status}' to under review."}, status=400)
        vendor.verification_status = Vendor.VerificationStatus.UNDER_REVIEW
        vendor.save(update_fields=["verification_status"])
        VendorVerificationLog.objects.create(
            vendor=vendor, reviewed_by=request.user, action=VendorVerificationLog.Action.MARKED_UNDER_REVIEW,
            notes=request.data.get("notes", ""),
        )
        return Response(AdminVendorSerializer(vendor).data)

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        serializer = RejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vendor = self.get_object()
        vendor.status = Vendor.Status.SUSPENDED
        vendor.save(update_fields=["status"])
        return Response(AdminVendorSerializer(vendor).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject_verification(self, request, pk=None):
        serializer = RejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vendor = self.get_object()
        vendor.verification_status = Vendor.VerificationStatus.REJECTED
        vendor.save(update_fields=["verification_status"])
        VendorVerificationLog.objects.create(
            vendor=vendor, reviewed_by=request.user, action=VendorVerificationLog.Action.REJECTED,
            notes=serializer.validated_data["reason"],
        )
        return Response(AdminVendorSerializer(vendor).data)

    @action(detail=True, methods=["post"], url_path="request-resubmission")
    def request_resubmission(self, request, pk=None):
        notes = request.data.get("notes", "")
        if not notes:
            return Response({"detail": "Explain what needs to be resubmitted."}, status=400)
        vendor = self.get_object()
        vendor.verification_status = Vendor.VerificationStatus.RESUBMISSION_REQUIRED
        vendor.save(update_fields=["verification_status"])
        VendorVerificationLog.objects.create(
            vendor=vendor, reviewed_by=request.user,
            action=VendorVerificationLog.Action.RESUBMISSION_REQUESTED, notes=notes,
        )
        return Response(AdminVendorSerializer(vendor).data)

    @action(detail=True, methods=["get"], url_path="verification-history")
    def verification_history(self, request, pk=None):
        vendor = self.get_object()
        logs = vendor.verification_logs.select_related("reviewed_by")
        return Response(VendorVerificationLogSerializer(logs, many=True).data)

    @action(detail=True, methods=["patch"])
    def commission(self, request, pk=None):
        serializer = AdminVendorCommissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vendor = self.get_object()
        vendor.commission_percent = serializer.validated_data["commission_percent"]
        vendor.save(update_fields=["commission_percent"])
        return Response(AdminVendorSerializer(vendor).data)


class AdminDeliveryPartnerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AdminDeliveryProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get_queryset(self):
        qs = DeliveryProfile.objects.select_related("user")
        status_filter = self.request.query_params.get("status")
        return qs.filter(status=status_filter) if status_filter else qs

    def get_permissions(self):
        if self.action in ("approve", "suspend", "reject_verification", "request_resubmission", "mark_under_review"):
            return [permissions.IsAuthenticated(), CanManageDeliveryPartners()]
        return [permissions.IsAuthenticated(), IsAdmin()]

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        profile = self.get_object()
        profile.status = DeliveryProfile.Status.APPROVED
        profile.verification_status = DeliveryProfile.VerificationStatus.APPROVED
        profile.save(update_fields=["status", "verification_status"])
        DeliveryVerificationLog.objects.create(
            delivery_profile=profile, reviewed_by=request.user, action=DeliveryVerificationLog.Action.APPROVED,
            notes=request.data.get("notes", ""),
        )
        return Response(AdminDeliveryProfileSerializer(profile).data)

    @action(detail=True, methods=["post"], url_path="mark-under-review")
    def mark_under_review(self, request, pk=None):
        profile = self.get_object()
        if profile.verification_status not in (DeliveryProfile.VerificationStatus.DOCUMENTS_SUBMITTED, DeliveryProfile.VerificationStatus.RESUBMISSION_REQUIRED):
            return Response({"detail": f"Can't move from '{profile.verification_status}' to under review."}, status=400)
        profile.verification_status = DeliveryProfile.VerificationStatus.UNDER_REVIEW
        profile.save(update_fields=["verification_status"])
        DeliveryVerificationLog.objects.create(
            delivery_profile=profile, reviewed_by=request.user, action=DeliveryVerificationLog.Action.MARKED_UNDER_REVIEW,
            notes=request.data.get("notes", ""),
        )
        return Response(AdminDeliveryProfileSerializer(profile).data)

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        profile = self.get_object()
        profile.status = DeliveryProfile.Status.SUSPENDED
        profile.is_online = False
        profile.save(update_fields=["status", "is_online"])
        return Response(AdminDeliveryProfileSerializer(profile).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject_verification(self, request, pk=None):
        serializer = RejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = self.get_object()
        profile.verification_status = DeliveryProfile.VerificationStatus.REJECTED
        profile.save(update_fields=["verification_status"])
        DeliveryVerificationLog.objects.create(
            delivery_profile=profile, reviewed_by=request.user, action=DeliveryVerificationLog.Action.REJECTED,
            notes=serializer.validated_data["reason"],
        )
        return Response(AdminDeliveryProfileSerializer(profile).data)

    @action(detail=True, methods=["post"], url_path="request-resubmission")
    def request_resubmission(self, request, pk=None):
        notes = request.data.get("notes", "")
        if not notes:
            return Response({"detail": "Explain what needs to be resubmitted."}, status=400)
        profile = self.get_object()
        profile.verification_status = DeliveryProfile.VerificationStatus.RESUBMISSION_REQUIRED
        profile.save(update_fields=["verification_status"])
        DeliveryVerificationLog.objects.create(
            delivery_profile=profile, reviewed_by=request.user,
            action=DeliveryVerificationLog.Action.RESUBMISSION_REQUESTED, notes=notes,
        )
        return Response(AdminDeliveryProfileSerializer(profile).data)

    @action(detail=True, methods=["get"], url_path="verification-history")
    def verification_history(self, request, pk=None):
        profile = self.get_object()
        logs = profile.verification_logs.select_related("reviewed_by")
        return Response(DeliveryVerificationLogSerializer(logs, many=True).data)


class AdminOrderViewSet(viewsets.ReadOnlyModelViewSet):
    """Platform-wide order visibility — every order, any vendor, any customer."""

    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["order_number", "customer__phone", "vendor__shop_name"]

    def get_queryset(self):
        qs = Order.objects.select_related("vendor", "customer").prefetch_related("items")
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("vendor"):
            qs = qs.filter(vendor_id=params["vendor"])
        if params.get("from"):
            qs = qs.filter(placed_at__date__gte=params["from"])
        if params.get("to"):
            qs = qs.filter(placed_at__date__lte=params["to"])
        return qs

    def get_serializer_class(self):
        return OrderListSerializer if self.action == "list" else OrderDetailSerializer


class AdminCouponViewSet(viewsets.ModelViewSet):
    queryset = Coupon.objects.all()
    serializer_class = AdminCouponSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated(), IsAdmin()]
        return [permissions.IsAuthenticated(), CanManageCoupons()]


class AdminCategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = AdminCategorySerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated(), IsAdmin()]
        return [permissions.IsAuthenticated(), CanManageCategories()]


class AdminBrandViewSet(viewsets.ModelViewSet):
    """
    Brand.name/slug are DB-unique — deleting a brand doesn't delete its
    products (FK is SET_NULL), so removing a brand just un-brands them.
    """

    queryset = Brand.objects.all()
    serializer_class = AdminBrandSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated(), IsAdmin()]
        # No dedicated can_manage_brands flag exists yet — brands are
        # catalog taxonomy like categories, so reuse that permission.
        return [permissions.IsAuthenticated(), CanManageCategories()]


class AdminProductViewSet(viewsets.ModelViewSet):
    """
    Full product CRUD for admin/super-admin — any shop, not just one the
    staff member owns. This is what lets super-admin add products (name,
    price, description, stock, images) directly from the console instead
    of going through a vendor account.
    """

    serializer_class = AdminProductSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "description", "sku", "barcode"]

    def get_queryset(self):
        qs = Product.objects.select_related("vendor", "category", "brand").prefetch_related("images").order_by("-created_at")
        vendor = self.request.query_params.get("vendor")
        category = self.request.query_params.get("category")
        if vendor:
            qs = qs.filter(vendor_id=vendor)
        if category:
            qs = qs.filter(category_id=category)
        return qs

    @action(detail=True, methods=["post"], url_path="images")
    def add_image(self, request, pk=None):
        """Upload one product image: multipart form with `image` file, optional `is_primary`."""
        product = self.get_object()
        if "image" not in request.FILES:
            return Response({"detail": "An `image` file is required."}, status=400)
        serializer = AdminProductImageSerializer(
            data={
                "image": request.FILES["image"],
                "is_primary": request.data.get("is_primary", False),
                "display_order": request.data.get("display_order", 0),
            }
        )
        serializer.is_valid(raise_exception=True)
        image = serializer.save(product=product)
        if image.is_primary:
            ProductImage.objects.filter(product=product).exclude(id=image.id).update(is_primary=False)
        return Response(AdminProductImageSerializer(image).data, status=201)

    @action(detail=True, methods=["delete"], url_path="images/(?P<image_id>[^/.]+)")
    def remove_image(self, request, pk=None, image_id=None):
        product = self.get_object()
        deleted, _ = ProductImage.objects.filter(product=product, id=image_id).delete()
        if not deleted:
            return Response({"detail": "Image not found."}, status=404)
        return Response(status=204)

    @action(detail=True, methods=["get", "post"], url_path="attributes")
    def attributes(self, request, pk=None):
        """GET lists this product's attributes; POST adds one."""
        product = self.get_object()
        if request.method == "GET":
            qs = product.attributes.all()
            return Response(AdminProductAttributeSerializer(qs, many=True).data)
        serializer = AdminProductAttributeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product)
        return Response(serializer.data, status=201)

    @action(detail=True, methods=["patch", "delete"], url_path="attributes/(?P<attribute_id>[^/.]+)")
    def attribute_detail(self, request, pk=None, attribute_id=None):
        product = self.get_object()
        attribute = get_object_or_404(ProductAttribute, product=product, id=attribute_id)
        if request.method == "DELETE":
            attribute.delete()
            return Response(status=204)
        serializer = AdminProductAttributeSerializer(attribute, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post"], url_path="variants")
    def variants(self, request, pk=None):
        """GET lists this product's variants; POST adds one."""
        product = self.get_object()
        if request.method == "GET":
            qs = product.variants.all()
            return Response(AdminProductVariantSerializer(qs, many=True).data)
        serializer = AdminProductVariantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product)
        return Response(serializer.data, status=201)

    @action(detail=True, methods=["patch", "delete"], url_path="variants/(?P<variant_id>[^/.]+)")
    def variant_detail(self, request, pk=None, variant_id=None):
        product = self.get_object()
        variant = get_object_or_404(ProductVariant, product=product, id=variant_id)
        if request.method == "DELETE":
            variant.delete()
            return Response(status=204)
        serializer = AdminProductVariantSerializer(variant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="export-csv")
    def export_csv(self, request):
        """Downloads every product as a CSV — same column layout `import-csv` expects."""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="products.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "vendor_name", "category_name", "name", "description", "unit", "mrp",
            "selling_price", "sku", "barcode", "stock_quantity", "is_available",
        ])
        for p in self.get_queryset():
            writer.writerow([
                p.vendor.shop_name, p.category.name, p.name, p.description, p.unit,
                p.mrp, p.selling_price, p.sku, p.barcode, p.stock_quantity, p.is_available,
            ])
        return response

    @action(detail=False, methods=["post"], url_path="import-csv")
    def import_csv(self, request):
        """
        Bulk-creates products from a CSV upload (multipart field `file`).
        Columns: vendor_name, category_name, name, description, unit, mrp,
        selling_price, sku, barcode, stock_quantity, is_available.
        `vendor_name` must match an existing shop name; `category_name` an
        existing category name (both case-insensitive) — rows that don't
        match are skipped and reported back, nothing else in the row is
        touched.
        """
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "A CSV `file` is required."}, status=400)

        try:
            decoded = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return Response({"detail": "Could not read the file — please upload UTF-8 CSV."}, status=400)

        reader = csv.DictReader(io.StringIO(decoded))
        created, errors = 0, []
        for i, row in enumerate(reader, start=2):  # row 1 is the header
            try:
                vendor = Vendor.objects.get(shop_name__iexact=(row.get("vendor_name") or "").strip())
                category = Category.objects.get(name__iexact=(row.get("category_name") or "").strip())
                Product.objects.create(
                    vendor=vendor,
                    category=category,
                    name=(row.get("name") or "").strip(),
                    description=row.get("description") or "",
                    unit=(row.get("unit") or "").strip(),
                    mrp=row.get("mrp") or 0,
                    selling_price=row.get("selling_price") or 0,
                    sku=row.get("sku") or "",
                    barcode=row.get("barcode") or "",
                    stock_quantity=row.get("stock_quantity") or 0,
                    is_available=str(row.get("is_available", "true")).strip().lower() in ("true", "1", "yes"),
                )
                created += 1
            except Vendor.DoesNotExist:
                errors.append(f"Row {i}: vendor '{row.get('vendor_name')}' not found.")
            except Category.DoesNotExist:
                errors.append(f"Row {i}: category '{row.get('category_name')}' not found.")
            except Exception as exc:  # noqa: BLE001 — surface any row-level bad data instead of failing the whole import
                errors.append(f"Row {i}: {exc}")

        return Response({"created": created, "errors": errors}, status=200 if created else 400)


class AdminLowStockView(APIView):
    """Low-stock products across every vendor on the platform."""

    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request):
        from apps.catalog.serializers import ProductListSerializer

        products = Product.objects.filter(stock_quantity__lte=10, stock_quantity__gt=0, is_available=True).select_related("vendor")
        return Response(ProductListSerializer(products, many=True, context={"request": request}).data)


class AdminExpiringStockView(APIView):
    """Batches expiring within 3 days across every vendor."""

    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request):
        from apps.inventory.serializers import StockBatchSerializer

        cutoff = timezone.localdate() + timezone.timedelta(days=3)
        batches = StockBatch.objects.filter(
            expiry_date__isnull=False, expiry_date__lte=cutoff, quantity__gt=0
        ).select_related("product__vendor")
        return Response(StockBatchSerializer(batches, many=True).data)


class AdminDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request):
        today = timezone.localdate()
        month_start = today.replace(day=1)

        users_by_role = dict(User.objects.values_list("role").annotate(c=Count("id")).order_by())
        vendors_by_status = dict(Vendor.objects.values_list("status").annotate(c=Count("id")).order_by())
        delivery_by_status = dict(DeliveryProfile.objects.values_list("status").annotate(c=Count("id")).order_by())

        orders_today = Order.objects.filter(placed_at__date=today)
        orders_this_month = Order.objects.filter(placed_at__date__gte=month_start)
        delivered_this_month = orders_this_month.filter(status=Order.Status.DELIVERED)

        revenue_this_month = delivered_this_month.aggregate(t=Sum("grand_total"))["t"] or 0

        return Response({
            "users": {"total": User.objects.count(), "by_role": users_by_role},
            "vendors": {
                "total": Vendor.objects.count(),
                "by_status": vendors_by_status,
                "pending_approval": vendors_by_status.get("pending", 0),
            },
            "delivery_partners": {
                "total": DeliveryProfile.objects.count(),
                "by_status": delivery_by_status,
                "pending_approval": delivery_by_status.get("pending", 0),
            },
            "orders": {
                "today": orders_today.count(),
                "this_month": orders_this_month.count(),
                "delivered_this_month": delivered_this_month.count(),
                "cancelled_this_month": orders_this_month.filter(status=Order.Status.CANCELLED).count(),
            },
            "revenue_this_month": revenue_this_month,
            "low_stock_products": Product.objects.filter(stock_quantity__lte=10, stock_quantity__gt=0, is_available=True).count(),
            "out_of_stock_products": Product.objects.filter(stock_quantity=0).count(),
        })


class AdminBroadcastNotificationView(APIView):
    """Sends a push notification to every user of a given role (or everyone)."""

    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request):
        from apps.core.task_utils import safe_delay
        from apps.notifications.tasks import send_push_notification_task

        serializer = BroadcastNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        qs = User.objects.filter(is_active=True)
        if data["role"] != "all":
            qs = qs.filter(role=data["role"])

        count = 0
        for user_id in qs.values_list("id", flat=True):
            safe_delay(send_push_notification_task, str(user_id), data["title"], data["message"])
            count += 1

        return Response({"detail": f"Notification queued for {count} user(s)."})


class AdminReviewViewSet(
    mixins.ListModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """Moderation: list every review platform-wide, approve/unapprove, or delete. Never create."""

    queryset = Review.objects.select_related("product", "customer").order_by("-created_at")
    serializer_class = AdminReviewSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["product__name", "customer__phone", "comment"]

    def get_queryset(self):
        qs = super().get_queryset()
        product_id = self.request.query_params.get("product")
        return qs.filter(product_id=product_id) if product_id else qs

    def perform_update(self, serializer):
        review = serializer.save()
        recalculate_product_rating(review.product)

    def perform_destroy(self, instance):
        product = instance.product
        instance.delete()
        recalculate_product_rating(product)


class AdminSliderViewSet(viewsets.ModelViewSet):
    queryset = Slider.objects.all()
    serializer_class = AdminSliderSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]


class AdminBannerViewSet(viewsets.ModelViewSet):
    queryset = Banner.objects.all()
    serializer_class = AdminBannerSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["title"]

    def get_queryset(self):
        qs = super().get_queryset()
        position = self.request.query_params.get("position")
        return qs.filter(position=position) if position else qs


class AdminOfferViewSet(viewsets.ModelViewSet):
    queryset = Offer.objects.all()
    serializer_class = AdminOfferSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["title", "discount_label"]


class AdminFAQViewSet(viewsets.ModelViewSet):
    queryset = FAQ.objects.all()
    serializer_class = AdminFAQSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["question", "answer"]


class AdminPageViewSet(viewsets.ModelViewSet):
    queryset = Page.objects.all()
    serializer_class = AdminPageSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["title"]


class AdminBlogPostViewSet(viewsets.ModelViewSet):
    queryset = BlogPost.objects.all()
    serializer_class = AdminBlogPostSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["title", "excerpt"]


class AdminFooterLinkViewSet(viewsets.ModelViewSet):
    queryset = FooterLink.objects.all()
    serializer_class = AdminFooterLinkSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        section = self.request.query_params.get("section")
        return qs.filter(section=section) if section else qs


class AdminContactMessageViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Admin triages submissions — read, mark status, delete. Never create (that's the public form's job)."""

    queryset = ContactMessage.objects.all()
    serializer_class = AdminContactMessageSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "email", "subject"]

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        return qs.filter(status=status_filter) if status_filter else qs


class AdminPaymentMethodConfigViewSet(viewsets.ModelViewSet):
    """Enable/disable payment methods, set a handling fee or minimum order value for each."""

    queryset = PaymentMethodConfig.objects.all()
    serializer_class = AdminPaymentMethodConfigSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]


class AdminExtraChargeViewSet(viewsets.ModelViewSet):
    """
    CRUD for admin-configured extra charges (handling / packing / night / rain
    or custom). A charge only affects checkout while is_active is True, so
    nothing shows to customers until an admin adds and enables it.
    """

    queryset = ExtraCharge.objects.all()
    serializer_class = AdminExtraChargeSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]


class AdminMediaAssetViewSet(viewsets.ModelViewSet):
    """
    Centralized upload library — upload once, reuse the URL anywhere.
    Deleting an asset here does NOT clean up references elsewhere (a
    banner/blog post that already used this file's URL keeps working off
    the stored URL string, since those fields aren't a FK to MediaAsset).
    """

    queryset = MediaAsset.objects.select_related("uploaded_by")
    serializer_class = AdminMediaAssetSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["alt_text"]

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class AdminWalletTransactionViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """
    Full wallet ledger, platform-wide. Admin can only ADD manual adjustment
    entries (never edit/delete history) — routed through the same
    credit_wallet/debit_wallet helpers customers' own transactions use, so
    a manual debit still can't push a wallet negative.
    """

    queryset = WalletTransaction.objects.select_related("user").order_by("-created_at")
    serializer_class = AdminWalletTransactionSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["user__phone", "user__full_name", "order_reference"]

    def get_queryset(self):
        qs = super().get_queryset()
        user_id = self.request.query_params.get("user")
        return qs.filter(user_id=user_id) if user_id else qs

    def perform_create(self, serializer):
        from apps.wallet.services import credit_wallet, debit_wallet

        data = serializer.validated_data
        fn = credit_wallet if data["type"] == WalletTransaction.Type.CREDIT else debit_wallet
        txn = fn(
            data["user"], data["amount"], WalletTransaction.Reason.ADMIN_ADJUSTMENT,
            order_reference=data.get("order_reference", ""), description=data.get("description", ""),
            created_by=self.request.user,
        )
        serializer.instance = txn


class AdminCampaignViewSet(viewsets.ModelViewSet):
    """Multi-channel marketing campaigns — Email/SMS/WhatsApp bulk sends + Facebook/Instagram posts."""

    queryset = Campaign.objects.select_related("audience_city", "created_by").order_by("-created_at")
    serializer_class = AdminCampaignSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Send now (ignores scheduled_at if set) — runs in the background via Celery."""
        campaign = self.get_object()
        if campaign.status in (Campaign.Status.SENDING, Campaign.Status.SENT):
            return Response({"detail": f"This campaign is already {campaign.status}."}, status=400)

        from apps.core.task_utils import safe_delay
        from apps.marketing.tasks import send_campaign_task

        campaign.status = Campaign.Status.SENDING
        campaign.save(update_fields=["status"])
        queued = safe_delay(send_campaign_task, str(campaign.id))
        if not queued:
            # No Celery broker reachable right now — run inline so "Send" still works locally/in dev.
            from apps.marketing.campaign_services import send_campaign

            send_campaign(str(campaign.id))
            campaign.refresh_from_db()

        return Response(AdminCampaignSerializer(campaign).data)

    @action(detail=True, methods=["post"], url_path="schedule")
    def schedule(self, request, pk=None):
        campaign = self.get_object()
        scheduled_at = request.data.get("scheduled_at")
        if not scheduled_at:
            return Response({"detail": "scheduled_at is required."}, status=400)
        campaign.scheduled_at = scheduled_at
        campaign.status = Campaign.Status.SCHEDULED
        campaign.save(update_fields=["scheduled_at", "status"])
        return Response(AdminCampaignSerializer(campaign).data)

    @action(detail=True, methods=["get"])
    def recipients(self, request, pk=None):
        campaign = self.get_object()
        qs = campaign.recipients.select_related("user").order_by("-sent_at")
        page = self.paginate_queryset(qs)
        serializer = CampaignRecipientSerializer(page or qs, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="audience-preview")
    def audience_preview(self, request, pk=None):
        """How many people this campaign would currently reach — lets the admin sanity-check before sending."""
        from apps.marketing.campaign_services import resolve_audience

        campaign = self.get_object()
        count = resolve_audience(campaign).count()
        return Response({"audience_count": count})

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        """Clone a campaign as a fresh draft — for re-running a past campaign or using it as a template."""
        original = self.get_object()
        copy = Campaign.objects.get(pk=original.pk)
        copy.pk = None
        copy.id = None
        copy.name = f"{original.name} (copy)"
        copy.status = Campaign.Status.DRAFT
        copy.total_recipients = copy.sent_count = copy.failed_count = 0
        copy.facebook_post_id = copy.facebook_error = copy.instagram_post_id = copy.instagram_error = ""
        copy.sent_at = None
        copy.created_by = request.user
        copy.save()
        copy.selected_customers.set(original.selected_customers.all())
        return Response(AdminCampaignSerializer(copy).data, status=201)

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        """
        Renders exactly what each enabled channel will show — the admin
        reviews this before anything actually sends. Nothing here has any
        side effect.
        """
        campaign = self.get_object()
        image_url = request.build_absolute_uri(campaign.image.url) if campaign.image else None
        link_suffix = f"\n\n{campaign.link_url}" if campaign.link_url else ""

        result = {}
        if campaign.send_email:
            result["email"] = {
                "subject": campaign.subject or campaign.name,
                "body": campaign.message + link_suffix,
                "image": image_url,
            }
        if campaign.send_sms:
            result["sms"] = {"body": campaign.message[:160]}
        if campaign.send_whatsapp:
            result["whatsapp"] = {"body": campaign.message + link_suffix, "image": image_url}
        if campaign.post_facebook:
            result["facebook"] = {"caption": campaign.message + link_suffix, "image": image_url}
        if campaign.post_instagram:
            result["instagram"] = {"caption": campaign.message + link_suffix, "image": image_url}
        return Response(result)

    @action(detail=False, methods=["get"], url_path="customers")
    def customers(self, request):
        """Searchable list for the individual-recipient picker."""
        from apps.accounts.models import Role, User

        search = request.query_params.get("search", "")
        qs = User.objects.filter(role=Role.CUSTOMER, is_active=True)
        if search:
            qs = qs.filter(
                Q(full_name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search)
            )
        qs = qs.order_by("full_name")[:50]
        return Response(SimpleCustomerSerializer(qs, many=True).data)

    @action(detail=True, methods=["get", "post"], url_path="external-contacts")
    def external_contacts(self, request, pk=None):
        campaign = self.get_object()
        if request.method == "GET":
            return Response(CampaignExternalContactSerializer(campaign.external_contacts.all(), many=True).data)
        serializer = CampaignExternalContactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(campaign=campaign)
        return Response(serializer.data, status=201)

    @action(detail=True, methods=["delete"], url_path="external-contacts/(?P<contact_id>[^/.]+)")
    def remove_external_contact(self, request, pk=None, contact_id=None):
        campaign = self.get_object()
        deleted, _ = campaign.external_contacts.filter(id=contact_id).delete()
        if not deleted:
            return Response({"detail": "Contact not found."}, status=404)
        return Response(status=204)

    @action(detail=False, methods=["post"], url_path="generate-ai-content")
    def generate_ai_content(self, request):
        """
        Drafts email/WhatsApp/social copy with AI — the admin reviews and
        edits it (it's just returned here, nothing is saved or sent).
        """
        from apps.marketing.ai_content import AIContentUnavailable, generate_campaign_content

        topic = request.data.get("topic", "")
        if not topic:
            return Response({"detail": "topic is required."}, status=400)
        try:
            content = generate_campaign_content(topic, product_name=request.data.get("product_name", ""))
        except AIContentUnavailable as exc:
            return Response({"detail": str(exc)}, status=503)
        return Response(content)


class AdminCampaignAnalyticsView(APIView):
    """Real-data dashboard for the Campaigns page — overview stats, recent-campaign delivery, contact growth."""

    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request):
        from datetime import timedelta

        from apps.accounts.models import Role, User
        from apps.marketing.models import Campaign, CampaignRecipient

        campaigns = Campaign.objects.all()
        by_status = dict(campaigns.values_list("status").annotate(c=Count("id")).order_by())

        emails_sent = CampaignRecipient.objects.filter(
            channel=CampaignRecipient.Channel.EMAIL, status=CampaignRecipient.Status.SENT
        ).count()
        whatsapp_sent = CampaignRecipient.objects.filter(
            channel=CampaignRecipient.Channel.WHATSAPP, status=CampaignRecipient.Status.SENT
        ).count()
        sms_sent = CampaignRecipient.objects.filter(
            channel=CampaignRecipient.Channel.SMS, status=CampaignRecipient.Status.SENT
        ).count()
        facebook_posts = campaigns.exclude(facebook_post_id="").count()
        instagram_posts = campaigns.exclude(instagram_post_id="").count()

        totals = campaigns.aggregate(recipients=Sum("total_recipients"), sent=Sum("sent_count"), failed=Sum("failed_count"))
        total_recipients = totals["recipients"] or 0
        total_sent = totals["sent"] or 0
        total_failed = totals["failed"] or 0
        delivery_rate = round((total_sent / total_recipients * 100), 1) if total_recipients else 0.0

        recent = campaigns.exclude(status=Campaign.Status.DRAFT).order_by("-sent_at", "-created_at").first()
        recent_campaign = None
        if recent:
            recent_delivery_rate = round((recent.sent_count / recent.total_recipients * 100), 1) if recent.total_recipients else 0.0
            recent_campaign = {
                "id": str(recent.id), "name": recent.name, "status": recent.status,
                "total_recipients": recent.total_recipients, "sent_count": recent.sent_count,
                "failed_count": recent.failed_count, "delivery_rate": recent_delivery_rate,
                "sent_at": recent.sent_at,
            }

        # Weekly new-vs-existing customer growth, last 6 weeks — same shape as
        # the "Recent Campaigns" contacts chart pattern.
        today = timezone.localdate()
        weeks = []
        running_total_cutoff = today - timedelta(days=7 * 6)
        existing_before_window = User.objects.filter(role=Role.CUSTOMER, date_joined__date__lt=running_total_cutoff).count()
        running_total = existing_before_window
        for i in range(6):
            week_start = running_total_cutoff + timedelta(days=7 * i)
            week_end = week_start + timedelta(days=6)
            new_this_week = User.objects.filter(
                role=Role.CUSTOMER, date_joined__date__gte=week_start, date_joined__date__lte=week_end
            ).count()
            running_total += new_this_week
            weeks.append({
                "label": f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d')}",
                "new_contacts": new_this_week,
                "total_contacts": running_total,
            })

        customers = User.objects.filter(role=Role.CUSTOMER, is_active=True)
        total_customers = customers.count()
        with_email = customers.exclude(email="").exclude(email__isnull=True).count()
        without_email = total_customers - with_email
        new_last_30_days = customers.filter(date_joined__gte=timezone.now() - timedelta(days=30)).count()

        return Response({
            "overview": {
                "total_campaigns": campaigns.count(),
                "total_recipients": total_recipients,
                "emails_sent": emails_sent,
                "whatsapp_sent": whatsapp_sent,
                "sms_sent": sms_sent,
                "facebook_posts": facebook_posts,
                "instagram_posts": instagram_posts,
                "delivery_rate": delivery_rate,
                "failed_count": total_failed,
            },
            "by_status": {
                "draft": by_status.get(Campaign.Status.DRAFT, 0),
                "scheduled": by_status.get(Campaign.Status.SCHEDULED, 0),
                "sending": by_status.get(Campaign.Status.SENDING, 0),
                "sent": by_status.get(Campaign.Status.SENT, 0),
                "partially_sent": by_status.get(Campaign.Status.PARTIALLY_SENT, 0),
                "failed": by_status.get(Campaign.Status.FAILED, 0),
            },
            "recent_campaign": recent_campaign,
            "contact_growth": weeks,
            "contacts_summary": {
                "total_customers": total_customers,
                "with_email": with_email,
                "without_email": without_email,
                "new_last_30_days": new_last_30_days,
            },
        })
