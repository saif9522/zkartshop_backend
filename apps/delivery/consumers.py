from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class OrderTrackingConsumer(AsyncJsonWebsocketConsumer):
    """
    One socket per order. Only the order's customer, its assigned delivery
    partner, or an admin/super_admin may connect. On connect, sends a
    snapshot of the current status + last known location; after that,
    receives live `status_update` and `location_update` pushes from
    apps.core.realtime.broadcast_to_order (called from the order/delivery
    services whenever something changes).
    """

    async def connect(self):
        self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
        user = self.scope["user"]

        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        allowed = await self._user_can_track(user, self.order_id)
        if not allowed:
            await self.close(code=4003)
            return

        self.group_name = f"order_{self.order_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        snapshot = await self._get_snapshot(self.order_id)
        await self.send_json({"type": "snapshot", **snapshot})

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Clients don't need to send anything — reserved for a future ping/pong keepalive.
        pass

    # --- group event handlers: method name must match the "type" sent in broadcast_to_order ---

    async def location_update(self, event):
        await self.send_json({
            "type": "location_update",
            "latitude": event["latitude"],
            "longitude": event["longitude"],
        })

    async def status_update(self, event):
        await self.send_json({
            "type": "status_update",
            "status": event["status"],
            "order_number": event["order_number"],
        })

    @database_sync_to_async
    def _user_can_track(self, user, order_id):
        from apps.orders.models import Order

        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return False
        return (
            order.customer_id == user.id
            or order.delivery_partner_id == user.id
            or user.role in ("admin", "super_admin")
        )

    @database_sync_to_async
    def _get_snapshot(self, order_id):
        from apps.orders.models import Order

        order = Order.objects.select_related("delivery_partner__delivery_profile").get(id=order_id)
        location = None
        partner = order.delivery_partner
        if partner and hasattr(partner, "delivery_profile"):
            profile = partner.delivery_profile
            if profile.current_latitude is not None:
                location = {
                    "latitude": str(profile.current_latitude),
                    "longitude": str(profile.current_longitude),
                }
        return {"status": order.status, "order_number": order.order_number, "location": location}
