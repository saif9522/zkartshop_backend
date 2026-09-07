from django.db.models import Sum
from django.http import Http404
from django.utils import timezone
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsVendor
from apps.catalog.models import Product
from apps.inventory.models import StockBatch
from apps.vendors.models import Vendor, VendorTransaction
from apps.vendors.serializers import (
    VendorNearbySerializer,
    VendorOnboardSerializer,
    VendorProfileSerializer,
    VendorTransactionSerializer,
)


class VendorOnboardView(generics.CreateAPIView):
    """A vendor-role user calls this once to register their shop (status starts 'pending')."""

    serializer_class = VendorOnboardSerializer
    permission_classes = [permissions.IsAuthenticated, IsVendor]

    def create(self, request, *args, **kwargs):
        if hasattr(request.user, "vendor_profile"):
            return Response({"detail": "Shop already registered."}, status=status.HTTP_400_BAD_REQUEST)
        return super().create(request, *args, **kwargs)


class VendorProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = VendorProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsVendor]

    def get_object(self):
        if not hasattr(self.request.user, "vendor_profile"):
            raise Http404("You haven't registered a shop yet — call /vendors/onboard/ first.")
        return self.request.user.vendor_profile


class VendorDashboardView(APIView):
    """
    Vendor home-screen summary: product/stock health, earnings snapshot,
    and today's order activity.
    """

    permission_classes = [permissions.IsAuthenticated, IsVendor]

    def get(self, request):
        from apps.orders.models import Order

        if not hasattr(request.user, "vendor_profile"):
            raise Http404("You haven't registered a shop yet — call /vendors/onboard/ first.")
        vendor = request.user.vendor_profile
        products = Product.objects.filter(vendor=vendor)
        low_stock = products.filter(stock_quantity__lte=10, stock_quantity__gt=0, is_available=True)
        out_of_stock = products.filter(stock_quantity=0)

        expiring_soon = StockBatch.objects.filter(
            product__vendor=vendor,
            expiry_date__isnull=False,
            expiry_date__lte=timezone.localdate() + timezone.timedelta(days=3),
            quantity__gt=0,
        ).count()

        balance = VendorTransaction.objects.filter(vendor=vendor).aggregate(total=Sum("amount"))["total"] or 0
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        this_month_credit = VendorTransaction.objects.filter(
            vendor=vendor, type=VendorTransaction.Type.CREDIT, created_at__gte=month_start
        ).aggregate(total=Sum("amount"))["total"] or 0

        todays_orders = Order.objects.filter(
            vendor=vendor, placed_at__date=timezone.localdate()
        ).exclude(status=Order.Status.CANCELLED)
        revenue_today = todays_orders.aggregate(total=Sum("grand_total"))["total"] or 0

        return Response({
            "shop_name": vendor.shop_name,
            "status": vendor.status,
            "is_open": vendor.is_open,
            "products": {
                "total": products.count(),
                "low_stock": low_stock.count(),
                "out_of_stock": out_of_stock.count(),
                "batches_expiring_soon": expiring_soon,
            },
            "earnings": {
                "balance": balance,
                "this_month_credited": this_month_credit,
            },
            "orders_today": todays_orders.count(),
            "revenue_today": revenue_today,
        })


class VendorTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """The vendor's own earnings ledger — credits, commission, payouts."""

    serializer_class = VendorTransactionSerializer
    permission_classes = [permissions.IsAuthenticated, IsVendor]

    def get_queryset(self):
        return VendorTransaction.objects.filter(vendor=self.request.user.vendor_profile)


class NearbyVendorsView(APIView):
    """
    Public — 'shops near me' for the customer app's home/browse screen.
    Returns approved, currently-open vendors within the platform's max
    delivery radius, closest first.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from apps.delivery.services import haversine_km
        from apps.superadmin.models import PlatformSettings

        try:
            lat = float(request.query_params["lat"])
            lng = float(request.query_params["lng"])
        except (KeyError, ValueError):
            return Response({"detail": "lat and lng query params are required."}, status=400)

        max_radius = float(PlatformSettings.load().max_delivery_radius_km)
        category = request.query_params.get("category")

        qs = Vendor.objects.filter(status=Vendor.Status.APPROVED, is_open=True)
        if category:
            qs = qs.filter(category=category)

        nearby = []
        for vendor in qs:
            if vendor.latitude is None or vendor.longitude is None:
                continue
            distance = haversine_km(lat, lng, vendor.latitude, vendor.longitude)
            if distance <= max_radius:
                vendor.distance_km = round(distance, 1)
                nearby.append(vendor)

        nearby.sort(key=lambda v: v.distance_km)
        return Response(VendorNearbySerializer(nearby, many=True).data)
