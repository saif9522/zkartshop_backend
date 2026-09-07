import logging
import math

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.orders.models import Order
from apps.orders.services import transition_order

logger = logging.getLogger(__name__)


def haversine_km(lat1, lon1, lat2, lon2):
    """Straight-line distance in km — used as the ETA fallback when Google Maps isn't reachable."""
    lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    r = 6371
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def get_route(origin_lat, origin_lng, dest_lat, dest_lng):
    """
    Route + ETA for the delivery partner's navigation screen.
    Uses Google Directions API when a key is configured; falls back to a
    straight-line haversine estimate (assuming ~20 km/h effective city speed)
    otherwise, so the app still works without live Maps access.
    Docs: https://developers.google.com/maps/documentation/directions
    """
    distance_km = haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)

    if settings.GOOGLE_MAPS_API_KEY:
        try:
            import requests

            response = requests.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params={
                    "origin": f"{origin_lat},{origin_lng}",
                    "destination": f"{dest_lat},{dest_lng}",
                    "key": settings.GOOGLE_MAPS_API_KEY,
                },
                timeout=8,
            )
            data = response.json()
            if data.get("status") == "OK":
                leg = data["routes"][0]["legs"][0]
                return {
                    "distance_km": round(leg["distance"]["value"] / 1000, 2),
                    "eta_minutes": round(leg["duration"]["value"] / 60),
                    "polyline": data["routes"][0]["overview_polyline"]["points"],
                    "source": "google_maps",
                }
            logger.warning("Directions API returned status=%s — falling back to haversine", data.get("status"))
        except Exception as exc:
            logger.warning("Directions API call failed (%s) — falling back to haversine", exc)

    return {
        "distance_km": round(distance_km, 2),
        "eta_minutes": max(2, round(distance_km / 20 * 60)),  # ~20 km/h effective city speed
        "polyline": None,
        "source": "estimated",
    }


@transaction.atomic
def assign_order(order_id, delivery_partner):
    """A delivery partner claims a READY, unassigned order."""
    order = get_object_or_404(Order.objects.select_for_update(), id=order_id)
    if order.status != Order.Status.READY:
        raise ValidationError("This order isn't ready for pickup.")
    if order.delivery_partner_id:
        raise ValidationError("This order has already been claimed by another delivery partner.")

    order.delivery_partner = delivery_partner
    order.save(update_fields=["delivery_partner"])
    return order


def confirm_pickup(order, delivery_partner, otp):
    _assert_owner(order, delivery_partner)
    if otp != order.pickup_otp:
        raise ValidationError("Incorrect pickup OTP.")
    return transition_order(order, Order.Status.PICKUP, actor=delivery_partner, vendor_initiated=False)


def start_delivery(order, delivery_partner):
    _assert_owner(order, delivery_partner)
    return transition_order(order, Order.Status.OUT_FOR_DELIVERY, actor=delivery_partner, vendor_initiated=False)


def mark_nearby(order, delivery_partner):
    _assert_owner(order, delivery_partner)
    return transition_order(order, Order.Status.NEARBY, actor=delivery_partner, vendor_initiated=False)


def confirm_delivery(order, delivery_partner, otp):
    _assert_owner(order, delivery_partner)
    if otp != order.delivery_otp:
        raise ValidationError("Incorrect delivery OTP.")
    return transition_order(order, Order.Status.DELIVERED, actor=delivery_partner, vendor_initiated=False)


def _assert_owner(order, delivery_partner):
    if order.delivery_partner_id != delivery_partner.id:
        raise ValidationError("This order isn't assigned to you.")


def update_location(delivery_partner, latitude, longitude):
    from apps.core.realtime import broadcast_to_order
    from apps.delivery.models import DeliveryProfile

    DeliveryProfile.objects.filter(user=delivery_partner).update(
        current_latitude=latitude, current_longitude=longitude, last_location_update=timezone.now()
    )

    active_orders = Order.objects.filter(
        delivery_partner=delivery_partner,
        status__in=[Order.Status.PICKUP, Order.Status.OUT_FOR_DELIVERY, Order.Status.NEARBY],
    )
    for order in active_orders:
        broadcast_to_order(
            str(order.id), "location_update", {"latitude": str(latitude), "longitude": str(longitude)}
        )
