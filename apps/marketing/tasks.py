import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def send_campaign_task(campaign_id):
    from apps.marketing.campaign_services import send_campaign

    try:
        campaign = send_campaign(campaign_id)
        logger.info(
            "Campaign %s sent: %s ok, %s failed", campaign_id, campaign.sent_count, campaign.failed_count
        )
    except Exception:
        logger.exception("Campaign %s failed to send", campaign_id)
        from apps.marketing.models import Campaign

        Campaign.objects.filter(id=campaign_id).update(status=Campaign.Status.FAILED)


@shared_task
def send_scheduled_campaigns():
    """Runs periodically (see celery.py beat_schedule) — dispatches any campaign whose scheduled time has arrived."""
    from django.utils import timezone

    from apps.marketing.models import Campaign

    due = Campaign.objects.filter(status=Campaign.Status.SCHEDULED, scheduled_at__lte=timezone.now())
    for campaign in due:
        send_campaign_task.delay(str(campaign.id))


@shared_task
def generate_product_launch_campaign_task(product_id):
    """
    Fires when a vendor publishes a new product. Drafts a ready-to-review
    campaign with AI-written copy across every channel — email, WhatsApp,
    Facebook, Instagram — using the product's own photo. This ALWAYS lands
    as a draft; nothing is ever sent without an admin reviewing it in
    Preview and clicking Send themselves.
    """
    from apps.catalog.models import Product
    from apps.marketing.ai_content import AIContentUnavailable, generate_campaign_content
    from apps.marketing.models import Campaign
    from apps.notifications.models import Notification
    from apps.notifications.services import notify_users

    try:
        product = Product.objects.select_related("vendor").get(id=product_id)
    except Product.DoesNotExist:
        logger.warning("generate_product_launch_campaign_task: product %s no longer exists", product_id)
        return

    try:
        content = generate_campaign_content(
            topic=f"New product launch — {product.name} at {product.vendor.shop_name}, ₹{product.selling_price}",
            product_name=product.name,
        )
    except AIContentUnavailable as exc:
        logger.info("Skipping auto-campaign for product %s: %s", product_id, exc)
        return

    primary_image = product.images.filter(is_primary=True).first() or product.images.first()

    campaign = Campaign.objects.create(
        name=f"New arrival — {product.name}",
        is_ai_generated=True,
        source_product=product,
        send_email=True,
        send_whatsapp=True,
        post_facebook=True,
        post_instagram=bool(primary_image),  # Instagram requires an image — skip it if the product has none yet
        audience=Campaign.Audience.ALL_CUSTOMERS,
        subject=content.get("email_subject", f"New arrival: {product.name}"),
        message=content.get("email_body", f"Check out {product.name}, now available on zKart.shop!"),
    )
    if primary_image:
        campaign.image = primary_image.image
        campaign.save(update_fields=["image"])

    from apps.accounts.models import Role, User

    notify_users(
        User.objects.filter(role__in=[Role.ADMIN, Role.SUPER_ADMIN], is_active=True),
        Notification.Type.SYSTEM,
        "AI drafted a launch campaign",
        f'"{product.name}" — review and send from Campaigns.',
        {"campaign_id": str(campaign.id)},
    )
    logger.info("Auto-drafted campaign %s for new product %s", campaign.id, product_id)
