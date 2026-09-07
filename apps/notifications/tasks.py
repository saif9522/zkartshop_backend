import logging

from celery import shared_task
from django.conf import settings

from apps.notifications.services import (
    EmailDeliveryError,
    SMSDeliveryError,
    send_otp_sms,
    send_transactional_email,
    send_transactional_sms,
)

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(SMSDeliveryError,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def send_otp_sms_task(self, phone: str, otp_code: str):
    """Sends the OTP via APITxT in the background so the API response isn't blocked on SMS delivery."""
    return send_otp_sms(phone, otp_code)


@shared_task(
    bind=True,
    autoretry_for=(SMSDeliveryError,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def send_transactional_sms_task(self, phone: str, message: str):
    """Order confirmations, out-for-delivery alerts, vendor payout notices, etc."""
    return send_transactional_sms(phone, message)


@shared_task
def send_whatsapp_message_task(phone: str, message: str):
    """
    WhatsApp notifications via APITxT's channel=whatsapp parameter on the
    same messaging endpoint used for SMS. Falls back to a dev-mode log when
    no API key is configured, same as the SMS tasks, so it's safe to call
    everywhere without a live WhatsApp Business account set up yet.
    """
    import requests

    mobile = phone.lstrip("+")
    if not settings.APITXT_API_KEY:
        logger.info("[DEV] WhatsApp to %s: %s (APITXT_API_KEY not set — not sending for real)", mobile, message)
        return {"status": "success", "message": "dev-mode: not actually sent"}

    try:
        response = requests.post(
            settings.APITXT_SEND_SMS_URL,
            data={
                "authkey": settings.APITXT_API_KEY,
                "sender": settings.APITXT_SENDER_ID,
                "mobiles": mobile,
                "message": message,
                "channel": "whatsapp",
            },
            timeout=10,
        )
        return response.json()
    except Exception as exc:
        logger.error("APITxT WhatsApp send failed for %s: %s", mobile, exc)
        return {"status": "error", "message": str(exc)}


@shared_task
def send_email_task(to_email: str, subject: str, body: str, html_body: str = None):
    """
    Order confirmations, vendor onboarding welcome, password reset, etc.
    Uses Django's EMAIL_BACKEND — console backend in dev (prints to the
    worker log), swap to SMTP in production settings.
    """
    from django.core.mail import EmailMultiAlternatives

    if not to_email:
        logger.warning("send_email_task called with no recipient — skipping")
        return {"status": "skipped", "reason": "no recipient"}

    email = EmailMultiAlternatives(
        subject=subject, body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=[to_email]
    )
    if html_body:
        email.attach_alternative(html_body, "text/html")
    sent = email.send(fail_silently=False)
    return {"status": "sent" if sent else "failed", "to": to_email}


@shared_task
def send_push_notification_task(user_id: str, title: str, body: str, data: dict = None):
    """
    Persists an in-app Notification (powers the notification bell/inbox)
    and logs an FCM push attempt. Real FCM delivery needs device tokens
    collected from the customer/vendor/delivery apps — wire that in once
    the mobile apps (Phase 10) register tokens; the in-app record works today.
    """
    from apps.accounts.models import User
    from apps.notifications.models import Notification

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning("send_push_notification_task: user %s not found — skipping", user_id)
        return {"status": "skipped", "reason": "user not found"}

    notification = Notification.objects.create(user=user, title=title, body=body, data=data or {})
    logger.info("[STUB FCM] Push to user %s: %s — %s (%s)", user_id, title, body, data or {})
    return {"status": "created", "notification_id": str(notification.id)}


@shared_task(
    bind=True,
    autoretry_for=(EmailDeliveryError,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def send_transactional_email_task(self, to_email: str, subject: str, body_text: str, body_html: str = None):
    """Sends an email in the background so the API response isn't blocked on SMTP delivery."""
    return send_transactional_email(to_email, subject, body_text, body_html)
