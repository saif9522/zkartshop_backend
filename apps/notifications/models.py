import uuid

from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        ORDER = "order", "Order update"
        PROMO = "promo", "Promotion / offer"
        SYSTEM = "system", "System"
        VENDOR = "vendor", "Vendor alert"
        DELIVERY = "delivery", "Delivery alert"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="notifications", on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.SYSTEM)
    title = models.CharField(max_length=150)
    body = models.CharField(max_length=500)
    data = models.JSONField(blank=True, null=True, help_text="Extra payload, e.g. {'order_id': '...'}")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read"])]

    def __str__(self):
        return f"{self.title} → {self.user}"


class PushSubscription(models.Model):
    """
    One row per browser/device a user has enabled push notifications on
    (PushManager.subscribe() on the frontend). A user can have several —
    phone + laptop, etc. — so pushes go out to all of them.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="push_subscriptions", on_delete=models.CASCADE)
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh_key = models.CharField(max_length=255)
    auth_key = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "push_subscriptions"

    def __str__(self):
        return f"{self.user} — {self.endpoint[:50]}"
