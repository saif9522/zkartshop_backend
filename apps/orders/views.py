from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsCustomer, IsVendor
from apps.cart.models import Cart
from apps.orders.invoice import invoice_pdf_response
from apps.orders.models import Coupon, Order, PaymentMethodConfig
from apps.orders.serializers import (
    AdvanceStatusSerializer,
    CancelOrderSerializer,
    CheckoutSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    PaymentVerifySerializer,
    VendorOrderDetailSerializer,
    VendorOrderListSerializer,
)
from apps.orders.services import checkout_cart, estimate_delivery, transition_order, validate_coupon, verify_razorpay_payment


class DeliveryEstimateView(APIView):
    """
    Preview distance + delivery charge per vendor in the cart, for a given
    address — lets the cart/checkout screen show this before the customer
    commits to an order (and before they might discover a vendor is out of range).
    """

    permission_classes = [permissions.IsAuthenticated, IsCustomer]

    def get(self, request):
        from apps.accounts.models import Address

        address_id = request.query_params.get("address_id")
        if not address_id:
            return Response({"detail": "address_id is required."}, status=400)
        try:
            address = Address.objects.get(id=address_id, user=request.user)
        except Address.DoesNotExist:
            return Response({"detail": "Address not found."}, status=404)

        cart = Cart.objects.filter(user=request.user).first()
        if not cart:
            return Response([])

        by_vendor = {}
        for item in cart.items.select_related("product__vendor"):
            vendor = item.product.vendor
            by_vendor.setdefault(vendor.id, {"vendor": vendor, "subtotal": 0})
            by_vendor[vendor.id]["subtotal"] += item.product.selling_price * item.quantity

        results = [estimate_delivery(v["subtotal"], v["vendor"], address) for v in by_vendor.values()]
        return Response(results)


class CheckoutView(APIView):
    """Converts the customer's cart into one Order per vendor."""

    permission_classes = [permissions.IsAuthenticated, IsCustomer]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        orders, grand_total, razorpay_payload = checkout_cart(
            user=request.user,
            address_id=serializer.validated_data["address_id"],
            payment_method=serializer.validated_data["payment_method"],
            coupon_code=serializer.validated_data.get("coupon_code") or None,
        )

        return Response(
            {
                "orders": OrderDetailSerializer(orders, many=True).data,
                "combined_grand_total": grand_total,
                "razorpay": razorpay_payload,
            },
            status=status.HTTP_201_CREATED,
        )


class PaymentVerifyView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsCustomer]

    def post(self, request):
        serializer = PaymentVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        orders = verify_razorpay_payment(user=request.user, **serializer.validated_data)
        return Response(OrderDetailSerializer(orders, many=True).data)


class CouponValidateView(APIView):
    """Preview a coupon's discount against the customer's current cart, before checkout."""

    permission_classes = [permissions.IsAuthenticated, IsCustomer]

    def get(self, request):
        code = request.query_params.get("code")
        if not code:
            return Response({"detail": "code query param is required."}, status=status.HTTP_400_BAD_REQUEST)

        cart, _ = Cart.objects.get_or_create(user=request.user)
        coupon, discount = validate_coupon(code, cart.subtotal)
        return Response({
            "code": coupon.code,
            "discount_amount": discount,
            "cart_subtotal": cart.subtotal,
            "new_total": cart.subtotal - discount,
        })


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """A customer's own orders."""

    permission_classes = [permissions.IsAuthenticated, IsCustomer]

    def get_queryset(self):
        qs = Order.objects.filter(customer=self.request.user).select_related("vendor").prefetch_related("items")
        status_filter = self.request.query_params.get("status")
        return qs.filter(status=status_filter) if status_filter else qs

    def get_serializer_class(self):
        return OrderListSerializer if self.action == "list" else OrderDetailSerializer

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        serializer = CancelOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = transition_order(
            order, Order.Status.CANCELLED, actor=request.user, vendor_initiated=False,
            reason=serializer.validated_data["reason"] or "Cancelled by customer",
        )
        return Response(OrderDetailSerializer(order).data)

    @action(detail=True, methods=["get"])
    def invoice(self, request, pk=None):
        """Download this order's bill as a PDF."""
        order = self.get_object()
        return invoice_pdf_response(order)

    @action(detail=True, methods=["get"])
    def track(self, request, pk=None):
        """Snapshot for the tracking page's initial load; the frontend then opens the WebSocket for live updates."""
        order = self.get_object()
        location = None
        partner = order.delivery_partner
        if partner and hasattr(partner, "delivery_profile"):
            profile = partner.delivery_profile
            if profile.current_latitude is not None:
                location = {"latitude": str(profile.current_latitude), "longitude": str(profile.current_longitude)}
        return Response({
            "status": order.status,
            "order_number": order.order_number,
            "location": location,
            "websocket_url": f"/ws/orders/{order.id}/track/",
        })


class VendorOrderViewSet(viewsets.ReadOnlyModelViewSet):
    """Incoming orders for the logged-in vendor's own shop."""

    permission_classes = [permissions.IsAuthenticated, IsVendor]

    def get_queryset(self):
        qs = Order.objects.filter(vendor__owner=self.request.user).select_related("customer").prefetch_related("items")
        status_filter = self.request.query_params.get("status")
        return qs.filter(status=status_filter) if status_filter else qs

    def get_serializer_class(self):
        return VendorOrderListSerializer if self.action == "list" else VendorOrderDetailSerializer

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        order = transition_order(self.get_object(), Order.Status.ACCEPTED, actor=request.user, vendor_initiated=True)
        return Response(VendorOrderDetailSerializer(order).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        serializer = CancelOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = transition_order(
            self.get_object(), Order.Status.CANCELLED, actor=request.user, vendor_initiated=True,
            reason=serializer.validated_data["reason"] or "Rejected by vendor",
        )
        return Response(VendorOrderDetailSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="advance-status")
    def advance_status(self, request, pk=None):
        serializer = AdvanceStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = transition_order(
            self.get_object(), serializer.validated_data["status"], actor=request.user, vendor_initiated=True,
        )
        return Response(VendorOrderDetailSerializer(order).data)

    @action(detail=True, methods=["get"])
    def invoice(self, request, pk=None):
        """Download this order's bill as a PDF (vendor's own shop orders only)."""
        order = self.get_object()
        return invoice_pdf_response(order)


class PaymentMethodsView(APIView):
    """Which payment methods to show at checkout. No config row for a method = it's available with no restrictions."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        configs = {c.code: c for c in PaymentMethodConfig.objects.all()}
        available = []
        for code, label in Order.PaymentMethod.choices:
            config = configs.get(code)
            if config and not config.is_enabled:
                continue
            available.append({
                "code": code,
                "label": (config.label if config and config.label else label),
                "extra_fee": config.extra_fee if config else 0,
                "min_order_value": config.min_order_value if config else None,
            })
        return Response(available)
