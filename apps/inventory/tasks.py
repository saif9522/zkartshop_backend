import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def check_expiring_stock():
    """
    Runs daily at 6 AM IST (see mall_of_garhwa/celery.py beat_schedule).
    Flags batches expiring within 3 days and notifies the owning vendor.
    """
    from apps.core.task_utils import safe_delay
    from apps.inventory.models import StockBatch
    from apps.notifications.tasks import send_push_notification_task

    cutoff = timezone.localdate() + timedelta(days=3)
    expiring = StockBatch.objects.filter(
        expiry_date__isnull=False, expiry_date__lte=cutoff, quantity__gt=0
    ).select_related("product__vendor__owner")

    notified = 0
    for batch in expiring:
        vendor_owner_id = batch.product.vendor.owner_id
        safe_delay(
            send_push_notification_task,
            str(vendor_owner_id),
            "Stock expiring soon",
            f"{batch.product.name} (batch {batch.batch_number or batch.id}) expires on {batch.expiry_date}",
            {"product_id": str(batch.product_id), "batch_id": str(batch.id)},
        )
        notified += 1

    logger.info(
        "check_expiring_stock: %s batch(es) expiring within 3 days, %s notification(s) queued",
        expiring.count(), notified,
    )
    return {"expiring_batches": expiring.count(), "notifications_queued": notified}
