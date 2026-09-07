import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# How long a vendor has to accept before we auto-cancel (Zepto-style ~5 min).
ORDER_ACCEPT_TIMEOUT_MINUTES = getattr(settings, "ORDER_ACCEPT_TIMEOUT_MINUTES", 5)


@shared_task
def auto_cancel_stale_orders():
    """
    Runs every 2 minutes (see mall_of_garhwa/celery.py beat_schedule).
    Cancels orders a vendor never accepted within the acceptance window,
    restocks the reserved items, and notifies the customer.
    """
    from apps.orders.models import Order
    from apps.orders.services import transition_order
    from apps.superadmin.models import PlatformSettings

    timeout_minutes = PlatformSettings.load().order_accept_timeout_minutes
    cutoff = timezone.now() - timedelta(minutes=timeout_minutes)
    stale = Order.objects.filter(status=Order.Status.PLACED, placed_at__lt=cutoff)

    cancelled = 0
    for order in stale:
        transition_order(
            order, Order.Status.CANCELLED, actor=None, vendor_initiated=False,
            reason="Auto-cancelled: vendor did not respond in time",
        )
        cancelled += 1

    logger.info("auto_cancel_stale_orders: cancelled %s stale order(s)", cancelled)
    return {"cancelled": cancelled}
