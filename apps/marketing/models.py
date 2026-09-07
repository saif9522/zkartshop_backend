import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ActiveNowQuerySet(models.QuerySet):
    """Shared 'is this live right now' filter for Slider/Banner/Offer."""

    def live(self):
        now = timezone.now()
        return self.filter(is_active=True).filter(
            models.Q(valid_from__isnull=True) | models.Q(valid_from__lte=now)
        ).filter(
            models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=now)
        )


class Slider(models.Model):
    """Homepage hero carousel — full-width rotating banners."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=150, blank=True)
    subtitle = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to="sliders/")
    link_url = models.CharField(max_length=255, blank=True, help_text="e.g. /product/some-slug or an external URL")
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ActiveNowQuerySet.as_manager()

    class Meta:
        db_table = "sliders"
        ordering = ["display_order", "-created_at"]

    def __str__(self):
        return self.title or f"Slider {self.id}"


class Banner(models.Model):
    """Smaller promotional banners placed at specific spots in the app."""

    class Position(models.TextChoices):
        HOME_TOP = "home_top", "Home — top"
        HOME_MIDDLE = "home_middle", "Home — middle"
        CATEGORY_PAGE = "category_page", "Category page"
        CART_PAGE = "cart_page", "Cart page"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=150, blank=True)
    image = models.ImageField(upload_to="banners/")
    link_url = models.CharField(max_length=255, blank=True)
    position = models.CharField(max_length=20, choices=Position.choices, default=Position.HOME_TOP)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ActiveNowQuerySet.as_manager()

    class Meta:
        db_table = "banners"
        ordering = ["position", "display_order", "-created_at"]
        indexes = [models.Index(fields=["position", "is_active"])]

    def __str__(self):
        return self.title or f"Banner {self.id}"


class Offer(models.Model):
    """A promotional deal card (e.g. 'Flash Sale — up to 50% off') shown on the homepage."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=150)
    description = models.CharField(max_length=500, blank=True)
    image = models.ImageField(upload_to="offers/", blank=True, null=True)
    discount_label = models.CharField(max_length=50, blank=True, help_text="e.g. 'Up to 50% off', 'Buy 1 Get 1'")
    link_url = models.CharField(max_length=255, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ActiveNowQuerySet.as_manager()

    class Meta:
        db_table = "offers"
        ordering = ["display_order", "-created_at"]

    def __str__(self):
        return self.title


class Campaign(models.Model):
    """
    One multi-channel marketing send — email/SMS/WhatsApp go out to a
    targeted audience of users (tracked per-recipient in CampaignRecipient);
    Facebook/Instagram are a single post to the store's own Page/Business
    account (no per-user "recipient" concept there — tracked directly on
    this row instead).
    """

    class Audience(models.TextChoices):
        ALL_CUSTOMERS = "all_customers", "All customers"
        CITY = "city", "Customers in a specific city"
        RECENT_BUYERS = "recent_buyers", "Ordered in the last 30 days"
        INACTIVE = "inactive", "No order in the last 60 days (win-back)"
        SELECTED = "selected", "Hand-picked customers"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        PARTIALLY_SENT = "partially_sent", "Partially sent (some channels/recipients failed)"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    is_ai_generated = models.BooleanField(default=False, help_text="Auto-drafted when a vendor published a new product")
    source_product = models.ForeignKey(
        "catalog.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="The product this campaign was auto-drafted for, if any",
    )

    # Channels — plain booleans rather than a M2M/multi-select field: simple
    # to toggle in a form, simple to query ("campaigns that used WhatsApp").
    send_email = models.BooleanField(default=False)
    send_sms = models.BooleanField(default=False)
    send_whatsapp = models.BooleanField(default=False)
    post_facebook = models.BooleanField(default=False)
    post_instagram = models.BooleanField(default=False)

    audience = models.CharField(max_length=20, choices=Audience.choices, default=Audience.ALL_CUSTOMERS)
    audience_city = models.ForeignKey(
        "superadmin.City", null=True, blank=True, on_delete=models.SET_NULL,
        help_text="Only used when audience='city'",
    )
    selected_customers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="+",
        help_text="Only used when audience='selected' — individually hand-picked recipients",
    )

    subject = models.CharField(max_length=200, blank=True, help_text="Email subject line")
    message = models.TextField(help_text="Body text — used for email/SMS/WhatsApp and as the social caption")
    image = models.ImageField(upload_to="campaigns/", blank=True, null=True, help_text="Used for email header + Facebook/Instagram posts")
    link_url = models.URLField(blank=True, help_text="Optional — included in email/social posts")

    scheduled_at = models.DateTimeField(null=True, blank=True, help_text="Leave blank to send immediately")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    total_recipients = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)

    facebook_post_id = models.CharField(max_length=100, blank=True)
    facebook_error = models.CharField(max_length=500, blank=True)
    instagram_post_id = models.CharField(max_length=100, blank=True)
    instagram_error = models.CharField(max_length=500, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "campaigns"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def channels(self):
        names = []
        if self.send_email:
            names.append("email")
        if self.send_sms:
            names.append("sms")
        if self.send_whatsapp:
            names.append("whatsapp")
        if self.post_facebook:
            names.append("facebook")
        if self.post_instagram:
            names.append("instagram")
        return names


class CampaignRecipient(models.Model):
    """Per-user, per-channel delivery tracking for the email/SMS/WhatsApp legs of a campaign."""

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped (no email/phone on file)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(Campaign, related_name="recipients", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    error = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "campaign_recipients"
        indexes = [models.Index(fields=["campaign", "channel", "status"])]
        constraints = [
            models.UniqueConstraint(fields=["campaign", "user", "channel"], name="unique_campaign_user_channel")
        ]

    def __str__(self):
        return f"{self.campaign.name} → {self.user} ({self.channel})"


class CampaignExternalContact(models.Model):
    """
    An ad-hoc recipient added directly to one campaign — not a platform
    User. Lets an admin email/WhatsApp someone outside the customer
    database (a local business contact, a press list, etc.) without
    needing to create a fake account for them.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(Campaign, related_name="external_contacts", on_delete=models.CASCADE)
    name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email_status = models.CharField(max_length=10, choices=CampaignRecipient.Status.choices, default=CampaignRecipient.Status.PENDING)
    whatsapp_status = models.CharField(max_length=10, choices=CampaignRecipient.Status.choices, default=CampaignRecipient.Status.PENDING)

    class Meta:
        db_table = "campaign_external_contacts"

    def __str__(self):
        return self.name or self.email or self.phone
