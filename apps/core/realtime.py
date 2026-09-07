"""
Shared broadcast helper — both apps.orders (status changes) and
apps.delivery (location pings) push into the same per-order group, so it
lives here rather than in either app to avoid a circular import.
"""
import logging

from apps.core.task_utils import run_with_timeout

logger = logging.getLogger(__name__)


def _do_broadcast(order_id, event_type, payload):
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning("No channel layer configured — skipping broadcast for order %s", order_id)
        return
    async_to_sync(channel_layer.group_send)(f"order_{order_id}", {"type": event_type, **payload})


def broadcast_to_order(order_id, event_type, payload):
    """
    Sends {"type": event_type, **payload} to every socket subscribed to this
    order. Live tracking is a nice-to-have on top of the core order flow —
    a broadcast failure or a slow/unreachable Redis (e.g. locally, without
    Redis running) must never add noticeable delay to checkout/status
    updates, so this is bounded by a hard timeout.
    """
    ok = run_with_timeout(_do_broadcast, order_id, event_type, payload, timeout=0.5)
    if not ok:
        logger.warning("Broadcast %s for order %s did not complete in time — continuing without it.", event_type, order_id)
