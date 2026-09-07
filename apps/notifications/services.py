"""
Client for APITxT (https://apitxt.com) — used for OTP delivery and
transactional SMS across the platform (order updates, delivery-boy alerts).

In development, when APITXT_API_KEY is not set, calls are logged to the
console instead of hitting the network, so the OTP flow keeps working
without a real key.
"""
import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SMSDeliveryError(Exception):
    """Raised when APITxT returns a failure or is unreachable — Celery retries on this."""


def _normalize_mobile(phone) -> str:
    """PhoneNumberField renders as +919876543210 — APITxT wants digits only, no plus."""
    return str(phone).lstrip("+")


def send_otp_sms(phone, otp_code: str) -> dict:
    """
    Sends a one-time password via APITxT's dedicated OTP endpoint.
    Docs: https://apitxt.com/otp-sms-api  (POST /api/sendOTP)
    """
    mobile = _normalize_mobile(phone)

    if not settings.APITXT_API_KEY:
        logger.info("[DEV] OTP for %s: %s (APITXT_API_KEY not set — not sending for real)", mobile, otp_code)
        return {"status": "success", "message": "dev-mode: not actually sent", "mobile": mobile}

    try:
        response = requests.post(
            settings.APITXT_SEND_OTP_URL,
            data={
                "authkey": settings.APITXT_API_KEY,
                "mobile": mobile,
                "otp": otp_code,
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("APITxT OTP send failed for %s: %s", mobile, exc)
        raise SMSDeliveryError(str(exc)) from exc

    if payload.get("status") != "success":
        logger.error("APITxT OTP send rejected for %s: %s", mobile, payload)
        raise SMSDeliveryError(payload.get("message", "Unknown APITxT error"))

    return payload


def send_transactional_sms(phone, message: str) -> dict:
    """
    General-purpose transactional SMS — order confirmations, delivery updates,
    vendor alerts. Docs: https://apitxt.com/bulksms (POST /api/sendMsg)
    """
    mobile = _normalize_mobile(phone)

    if not settings.APITXT_API_KEY:
        logger.info("[DEV] SMS to %s: %s (APITXT_API_KEY not set — not sending for real)", mobile, message)
        return {"status": "success", "message": "dev-mode: not actually sent", "mobile": mobile}

    try:
        response = requests.post(
            settings.APITXT_SEND_SMS_URL,
            data={
                "authkey": settings.APITXT_API_KEY,
                "sender": settings.APITXT_SENDER_ID,
                "mobiles": mobile,
                "message": message,
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("APITxT SMS send failed for %s: %s", mobile, exc)
        raise SMSDeliveryError(str(exc)) from exc

    if payload.get("status") != "success":
        logger.error("APITxT SMS send rejected for %s: %s", mobile, payload)
        raise SMSDeliveryError(payload.get("message", "Unknown APITxT error"))

    return payload


def notify_user(user, notif_type, title, body, data=None):
    """
    Create one in-app notification (shows up in the bell icon) and attempt
    a real browser push to every device the user has subscribed on. Never
    raises — a failure here must not break the caller's main flow (e.g.
    checkout succeeding shouldn't hinge on a notification row insert).
    """
    from apps.core.task_utils import run_with_timeout
    from apps.notifications.models import Notification

    notification = None
    try:
        notification = Notification.objects.create(user=user, type=notif_type, title=title, body=body, data=data or {})
    except Exception:
        logger.exception("Failed to create notification for user %s", getattr(user, "id", None))

    run_with_timeout(send_web_push_to_user, user, title, body, data=data, timeout=1.0)
    return notification


def notify_users(users, notif_type, title, body, data=None):
    """Bulk-create the same notification for many users (e.g. every admin, every online delivery partner)."""
    from apps.core.task_utils import run_with_timeout
    from apps.notifications.models import Notification

    users = list(users)
    if not users:
        return
    try:
        Notification.objects.bulk_create(
            [Notification(user=u, type=notif_type, title=title, body=body, data=data or {}) for u in users]
        )
    except Exception:
        logger.exception("Failed to bulk-create notifications")

    def _push_all():
        for u in users:
            send_web_push_to_user(u, title, body, data=data)

    # One bounded call regardless of how many recipients — the caller's wait
    # time must not scale with the size of `users` (could be every admin,
    # every online delivery partner, etc).
    run_with_timeout(_push_all, timeout=1.5)


class EmailDeliveryError(Exception):
    pass


def send_transactional_email(to_email, subject, body_text, body_html=None):
    """
    Sends one email via Django's configured EMAIL_BACKEND (console locally,
    real SMTP in production once EMAIL_HOST_USER/PASSWORD are set). Raises
    EmailDeliveryError on failure so the Celery task's autoretry can kick in.
    """
    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives

    if not to_email:
        logger.warning("send_transactional_email: no recipient email — skipping '%s'", subject)
        return

    try:
        message = EmailMultiAlternatives(subject=subject, body=body_text, to=[to_email])
        if body_html:
            message.attach_alternative(body_html, "text/html")
        message.send(fail_silently=False)
    except Exception as exc:
        logger.error("Email send failed to %s (%s): %s", to_email, subject, exc)
        raise EmailDeliveryError(str(exc)) from exc


def send_web_push(subscription, title, body, data=None, url=None):
    """
    Sends one real browser push notification via the Web Push protocol.
    Returns True if delivered. If the browser has revoked/expired the
    subscription (410 Gone / 404), deletes it so we stop retrying a dead
    endpoint — that's normal churn, not an error worth alerting on.
    """
    from django.conf import settings
    from pywebpush import WebPushException, webpush

    if not settings.VAPID_PRIVATE_KEY_PEM:
        logger.info("[DEV] Web push to %s: %s — %s (VAPID keys not set — not sending for real)", subscription.user_id, title, body)
        return False

    payload = json.dumps({"title": title, "body": body, "data": data or {}, "url": url or "/"})
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh_key, "auth": subscription.auth_key},
            },
            data=payload,
            vapid_private_pem=settings.VAPID_PRIVATE_KEY_PEM.encode(),
            vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
        )
        return True
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            subscription.delete()
            logger.info("Push subscription for user %s expired — removed.", subscription.user_id)
        else:
            logger.error("Web push failed for user %s: %s", subscription.user_id, exc)
        return False


def send_web_push_to_user(user, title, body, data=None, url=None):
    """Pushes to every device the user has subscribed on."""
    from apps.notifications.models import PushSubscription

    sent = 0
    for sub in PushSubscription.objects.filter(user=user):
        if send_web_push(sub, title, body, data=data, url=url):
            sent += 1
    return sent
