from django.db.models import Sum
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsDeliveryPartner
from apps.delivery.models import Attendance, DeliveryProfile, DeliveryTransaction
from apps.delivery.serializers import (
    AttendanceSerializer,
    AvailableOrderSerializer,
    DeliveryOnboardSerializer,
    DeliveryProfileSerializer,
    DeliveryTransactionSerializer,
    LocationUpdateSerializer,
    MyDeliveryOrderSerializer,
    OTPSerializer,
)
from apps.delivery.services import (
    assign_order,
    confirm_delivery,
    confirm_pickup,
    get_route,
    mark_nearby,
    start_delivery,
    update_location,
)
from apps.orders.models import Order


class DeliveryOnboardView(generics.CreateAPIView):
    serializer_class = DeliveryOnboardSerializer
    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def create(self, request, *args, **kwargs):
        if hasattr(request.user, "delivery_profile"):
            return Response({"detail": "Delivery profile already registered."}, status=status.HTTP_400_BAD_REQUEST)
        return super().create(request, *args, **kwargs)


class DeliveryProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = DeliveryProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def get_object(self):
        if not hasattr(self.request.user, "delivery_profile"):
            raise Http404("You haven't registered as a delivery partner yet — call /delivery/onboard/ first.")
        return self.request.user.delivery_profile


class GoOnlineView(APIView):
    """Toggle online/offline — only online, approved partners see the order pool."""

    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def post(self, request):
        if not hasattr(request.user, "delivery_profile"):
            raise Http404("You haven't registered as a delivery partner yet — call /delivery/onboard/ first.")
        profile = request.user.delivery_profile
        profile.is_online = bool(request.data.get("is_online", not profile.is_online))
        profile.save(update_fields=["is_online"])
        return Response(DeliveryProfileSerializer(profile).data)


class LocationUpdateView(APIView):
    """
    Delivery partner's app pings this periodically while on a delivery.
    REST-polling for now — Phase 8 adds a WebSocket channel so the customer
    sees this move live on their tracking map without polling.
    """

    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def post(self, request):
        serializer = LocationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        update_location(request.user, **serializer.validated_data)
        return Response({"detail": "Location updated."})


class DeliveryDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def get(self, request):
        if not hasattr(request.user, "delivery_profile"):
            raise Http404("You haven't registered as a delivery partner yet — call /delivery/onboard/ first.")
        profile = request.user.delivery_profile
        today = timezone.localdate()

        active_orders = Order.objects.filter(
            delivery_partner=request.user,
            status__in=[
                Order.Status.READY, Order.Status.PICKUP, Order.Status.OUT_FOR_DELIVERY, Order.Status.NEARBY,
            ],
        ).count()
        delivered_today = Order.objects.filter(
            delivery_partner=request.user, status=Order.Status.DELIVERED, delivered_at__date=today
        ).count()

        balance = DeliveryTransaction.objects.filter(delivery_partner=request.user).aggregate(t=Sum("amount"))["t"] or 0
        today_earning = DeliveryTransaction.objects.filter(
            delivery_partner=request.user, type=DeliveryTransaction.Type.DELIVERY_EARNING, created_at__date=today
        ).aggregate(t=Sum("amount"))["t"] or 0

        return Response({
            "status": profile.status,
            "is_online": profile.is_online,
            "active_orders": active_orders,
            "delivered_today": delivered_today,
            "earnings": {"balance": balance, "today": today_earning},
        })


class AvailableOrdersView(APIView):
    """The pool of READY, unassigned orders a delivery partner can claim."""

    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def get(self, request):
        orders = Order.objects.filter(status=Order.Status.READY, delivery_partner__isnull=True).select_related("vendor")
        return Response(AvailableOrderSerializer(orders, many=True).data)


class AssignOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def post(self, request, order_id):
        order = assign_order(order_id, request.user)
        return Response(MyDeliveryOrderSerializer(order).data)


class MyDeliveryOrdersView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def get(self, request):
        qs = Order.objects.filter(delivery_partner=request.user).select_related("vendor", "delivery_address")
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(MyDeliveryOrderSerializer(qs, many=True).data)


def _get_own_order(request, order_id):
    return get_object_or_404(Order, id=order_id, delivery_partner=request.user)


class ConfirmPickupView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def post(self, request, order_id):
        serializer = OTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = confirm_pickup(_get_own_order(request, order_id), request.user, serializer.validated_data["otp"])
        return Response(MyDeliveryOrderSerializer(order).data)


class StartDeliveryView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def post(self, request, order_id):
        order = start_delivery(_get_own_order(request, order_id), request.user)
        return Response(MyDeliveryOrderSerializer(order).data)


class MarkNearbyView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def post(self, request, order_id):
        order = mark_nearby(_get_own_order(request, order_id), request.user)
        return Response(MyDeliveryOrderSerializer(order).data)


class ConfirmDeliveryView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def post(self, request, order_id):
        serializer = OTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = confirm_delivery(_get_own_order(request, order_id), request.user, serializer.validated_data["otp"])
        return Response(MyDeliveryOrderSerializer(order).data)


class RouteView(APIView):
    """Navigation target: the vendor's shop before pickup, the customer's address after."""

    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def get(self, request, order_id):
        order = _get_own_order(request, order_id)
        if not hasattr(request.user, "delivery_profile"):
            raise Http404("You haven't registered as a delivery partner yet — call /delivery/onboard/ first.")
        profile = request.user.delivery_profile
        if profile.current_latitude is None:
            return Response({"detail": "Share your current location first."}, status=status.HTTP_400_BAD_REQUEST)

        if order.status in (Order.Status.PICKUP, Order.Status.OUT_FOR_DELIVERY, Order.Status.NEARBY):
            dest_lat, dest_lng, label = order.delivery_address.latitude, order.delivery_address.longitude, "customer"
        else:
            dest_lat, dest_lng, label = order.vendor.latitude, order.vendor.longitude, "vendor"

        route = get_route(profile.current_latitude, profile.current_longitude, dest_lat, dest_lng)
        route["destination"] = label
        return Response(route)


class DeliveryTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DeliveryTransactionSerializer
    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def get_queryset(self):
        return DeliveryTransaction.objects.filter(delivery_partner=self.request.user)


class AttendanceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def get_queryset(self):
        return Attendance.objects.filter(delivery_partner=self.request.user)


class CheckInView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def post(self, request):
        today = timezone.localdate()
        attendance, created = Attendance.objects.get_or_create(delivery_partner=request.user, date=today)
        if attendance.check_in_time:
            return Response({"detail": "Already checked in today."}, status=status.HTTP_400_BAD_REQUEST)
        attendance.check_in_time = timezone.now()
        attendance.save(update_fields=["check_in_time"])
        return Response(AttendanceSerializer(attendance).data)


class CheckOutView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsDeliveryPartner]

    def post(self, request):
        today = timezone.localdate()
        try:
            attendance = Attendance.objects.get(delivery_partner=request.user, date=today, check_in_time__isnull=False)
        except Attendance.DoesNotExist:
            return Response({"detail": "You haven't checked in today."}, status=status.HTTP_400_BAD_REQUEST)
        attendance.check_out_time = timezone.now()
        attendance.save(update_fields=["check_out_time"])
        return Response(AttendanceSerializer(attendance).data)
