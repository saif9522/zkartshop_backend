import logging

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class SocialPostError(Exception):
    pass


def resolve_audience(campaign):
    """Returns the queryset of users this campaign should reach, based on campaign.audience."""
    from datetime import timedelta

    from apps.accounts.models import Role, User
    from apps.orders.models import Order

    base = User.objects.filter(role=Role.CUSTOMER, is_active=True)

    if campaign.audience == campaign.Audience.SELECTED:
        return campaign.selected_customers.filter(is_active=True)

    if campaign.audience == campaign.Audience.CITY and campaign.audience_city:
        return base.filter(addresses__city__iexact=campaign.audience_city.name).distinct()

    if campaign.audience == campaign.Audience.RECENT_BUYERS:
        since = timezone.now() - timedelta(days=30)
        return base.filter(orders__placed_at__gte=since).distinct()

    if campaign.audience == campaign.Audience.INACTIVE:
        since = timezone.now() - timedelta(days=60)
        recent_buyer_ids = Order.objects.filter(placed_at__gte=since).values_list("customer_id", flat=True)
        return base.exclude(id__in=recent_buyer_ids)

    return base


def _absolute_media_url(image_field):
    if not image_field:
        return None
    url = image_field.url
    if url.startswith("http"):
        return url
    return settings.SITE_URL.rstrip("/") + url


def post_to_facebook(campaign):
    """Posts to the store's Facebook Page — a photo post if an image is attached, otherwise a text post."""
    if not (settings.FACEBOOK_PAGE_ACCESS_TOKEN and settings.FACEBOOK_PAGE_ID):
        raise SocialPostError("Facebook isn't configured (FACEBOOK_PAGE_ACCESS_TOKEN / FACEBOOK_PAGE_ID missing).")

    base = f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/{settings.FACEBOOK_PAGE_ID}"
    image_url = _absolute_media_url(campaign.image)
    message = campaign.message + (f"\n\n{campaign.link_url}" if campaign.link_url else "")

    if image_url:
        response = requests.post(
            f"{base}/photos",
            data={"url": image_url, "caption": message, "access_token": settings.FACEBOOK_PAGE_ACCESS_TOKEN},
            timeout=30,
        )
    else:
        params = {"message": message, "access_token": settings.FACEBOOK_PAGE_ACCESS_TOKEN}
        if campaign.link_url:
            params["link"] = campaign.link_url
        response = requests.post(f"{base}/feed", data=params, timeout=30)

    data = response.json()
    if "error" in data:
        raise SocialPostError(data["error"].get("message", "Unknown Facebook API error"))
    return data.get("post_id") or data.get("id")


def post_to_instagram(campaign):
    """
    Instagram Business posting is a two-step Graph API dance: create a media
    container, then publish it. An image is required — Instagram has no
    text-only post type.
    """
    if not (settings.FACEBOOK_PAGE_ACCESS_TOKEN and settings.INSTAGRAM_BUSINESS_ACCOUNT_ID):
        raise SocialPostError("Instagram isn't configured (FACEBOOK_PAGE_ACCESS_TOKEN / INSTAGRAM_BUSINESS_ACCOUNT_ID missing).")

    image_url = _absolute_media_url(campaign.image)
    if not image_url:
        raise SocialPostError("Instagram posts require an image — this campaign has none attached.")

    base = f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/{settings.INSTAGRAM_BUSINESS_ACCOUNT_ID}"
    message = campaign.message + (f"\n\n{campaign.link_url}" if campaign.link_url else "")

    container_resp = requests.post(
        f"{base}/media",
        data={"image_url": image_url, "caption": message, "access_token": settings.FACEBOOK_PAGE_ACCESS_TOKEN},
        timeout=30,
    )
    container_data = container_resp.json()
    if "error" in container_data:
        raise SocialPostError(container_data["error"].get("message", "Unknown Instagram API error (container)"))

    creation_id = container_data["id"]
    publish_resp = requests.post(
        f"{base}/media_publish",
        data={"creation_id": creation_id, "access_token": settings.FACEBOOK_PAGE_ACCESS_TOKEN},
        timeout=30,
    )
    publish_data = publish_resp.json()
    if "error" in publish_data:
        raise SocialPostError(publish_data["error"].get("message", "Unknown Instagram API error (publish)"))

    return publish_data.get("id")


def send_campaign(campaign_id):
    """
    Runs the full send: resolves the audience, sends email/SMS/WhatsApp to
    each recipient (tracked per-channel in CampaignRecipient), posts to
    Facebook/Instagram if enabled, and updates the campaign's status/counts.
    Safe to call synchronously (small audience) or from a Celery task.
    """
    from apps.marketing.models import Campaign, CampaignRecipient
    from apps.notifications.services import send_transactional_email, send_transactional_sms
    from apps.notifications.tasks import send_whatsapp_message_task

    campaign = Campaign.objects.get(id=campaign_id)
    campaign.status = Campaign.Status.SENDING
    campaign.save(update_fields=["status"])

    sent = 0
    failed = 0

    if campaign.send_email or campaign.send_sms or campaign.send_whatsapp:
        audience = list(resolve_audience(campaign))
        campaign.total_recipients = len(audience)
        campaign.save(update_fields=["total_recipients"])

        for user in audience:
            if campaign.send_email:
                if user.email:
                    try:
                        send_transactional_email(user.email, campaign.subject or campaign.name, campaign.message)
                        CampaignRecipient.objects.update_or_create(
                            campaign=campaign, user=user, channel=CampaignRecipient.Channel.EMAIL,
                            defaults={"status": CampaignRecipient.Status.SENT, "sent_at": timezone.now()},
                        )
                        sent += 1
                    except Exception as exc:
                        CampaignRecipient.objects.update_or_create(
                            campaign=campaign, user=user, channel=CampaignRecipient.Channel.EMAIL,
                            defaults={"status": CampaignRecipient.Status.FAILED, "error": str(exc)[:255]},
                        )
                        failed += 1
                else:
                    CampaignRecipient.objects.update_or_create(
                        campaign=campaign, user=user, channel=CampaignRecipient.Channel.EMAIL,
                        defaults={"status": CampaignRecipient.Status.SKIPPED, "error": "No email on file"},
                    )

            if campaign.send_sms and user.phone:
                try:
                    send_transactional_sms(str(user.phone), campaign.message)
                    CampaignRecipient.objects.update_or_create(
                        campaign=campaign, user=user, channel=CampaignRecipient.Channel.SMS,
                        defaults={"status": CampaignRecipient.Status.SENT, "sent_at": timezone.now()},
                    )
                    sent += 1
                except Exception as exc:
                    CampaignRecipient.objects.update_or_create(
                        campaign=campaign, user=user, channel=CampaignRecipient.Channel.SMS,
                        defaults={"status": CampaignRecipient.Status.FAILED, "error": str(exc)[:255]},
                    )
                    failed += 1

            if campaign.send_whatsapp and user.phone:
                try:
                    send_whatsapp_message_task(str(user.phone), campaign.message)
                    CampaignRecipient.objects.update_or_create(
                        campaign=campaign, user=user, channel=CampaignRecipient.Channel.WHATSAPP,
                        defaults={"status": CampaignRecipient.Status.SENT, "sent_at": timezone.now()},
                    )
                    sent += 1
                except Exception as exc:
                    CampaignRecipient.objects.update_or_create(
                        campaign=campaign, user=user, channel=CampaignRecipient.Channel.WHATSAPP,
                        defaults={"status": CampaignRecipient.Status.FAILED, "error": str(exc)[:255]},
                    )
                    failed += 1

    for contact in campaign.external_contacts.all():
        if campaign.send_email and contact.email:
            try:
                send_transactional_email(contact.email, campaign.subject or campaign.name, campaign.message)
                contact.email_status = CampaignRecipient.Status.SENT
                sent += 1
            except Exception:
                contact.email_status = CampaignRecipient.Status.FAILED
                failed += 1
            contact.save(update_fields=["email_status"])

        if campaign.send_whatsapp and contact.phone:
            try:
                send_whatsapp_message_task(contact.phone, campaign.message)
                contact.whatsapp_status = CampaignRecipient.Status.SENT
                sent += 1
            except Exception:
                contact.whatsapp_status = CampaignRecipient.Status.FAILED
                failed += 1
            contact.save(update_fields=["whatsapp_status"])

    social_failed = False
    if campaign.post_facebook:
        try:
            campaign.facebook_post_id = post_to_facebook(campaign)
            campaign.facebook_error = ""
        except Exception as exc:
            campaign.facebook_error = str(exc)[:500]
            social_failed = True
            logger.error("Facebook post failed for campaign %s: %s", campaign.id, exc)

    if campaign.post_instagram:
        try:
            campaign.instagram_post_id = post_to_instagram(campaign)
            campaign.instagram_error = ""
        except Exception as exc:
            campaign.instagram_error = str(exc)[:500]
            social_failed = True
            logger.error("Instagram post failed for campaign %s: %s", campaign.id, exc)

    campaign.sent_count = sent
    campaign.failed_count = failed
    campaign.sent_at = timezone.now()
    if failed == 0 and not social_failed:
        campaign.status = Campaign.Status.SENT
    elif sent > 0 or (not social_failed and (campaign.post_facebook or campaign.post_instagram)):
        campaign.status = Campaign.Status.PARTIALLY_SENT
    else:
        campaign.status = Campaign.Status.FAILED
    campaign.save(update_fields=[
        "sent_count", "failed_count", "sent_at", "status",
        "facebook_post_id", "facebook_error", "instagram_post_id", "instagram_error",
    ])

    return campaign
