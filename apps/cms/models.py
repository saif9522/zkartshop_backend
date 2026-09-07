import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class FAQ(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.CharField(max_length=300)
    answer = models.TextField()
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "faqs"
        ordering = ["display_order", "-created_at"]

    def __str__(self):
        return self.question


class Page(models.Model):
    """Generic static page — About Us, Privacy Policy, Terms, Refund Policy, etc."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    content = models.TextField(help_text="Markdown or plain text, rendered as-is by the frontend")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pages"
        ordering = ["title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)[:160] or "page"
            slug = base_slug
            while Page.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
            self.slug = slug
        super().save(*args, **kwargs)


class BlogPost(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    excerpt = models.CharField(max_length=300, blank=True)
    content = models.TextField(help_text="Markdown or plain text, rendered as-is by the frontend")
    cover_image = models.ImageField(upload_to="blog/", blank=True, null=True)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "blog_posts"
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)[:200] or "post"
            slug = base_slug
            while BlogPost.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
            self.slug = slug
        if self.is_published and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)


class FooterLink(models.Model):
    class Section(models.TextChoices):
        ABOUT = "about", "About"
        QUICK_LINKS = "quick_links", "Quick Links"
        CUSTOMER_SUPPORT = "customer_support", "Customer Support"
        SOCIAL = "social", "Social Media"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.CharField(max_length=20, choices=Section.choices)
    label = models.CharField(max_length=100)
    url = models.CharField(max_length=255)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "footer_links"
        ordering = ["section", "display_order"]
        indexes = [models.Index(fields=["section", "is_active"])]

    def __str__(self):
        return f"[{self.section}] {self.label}"


class ContactMessage(models.Model):
    """Public contact-form submissions — customers create, admins triage."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        READ = "read", "Read"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contact_messages"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self):
        return f"{self.subject} — {self.name}"


class MediaAsset(models.Model):
    """
    Centralized upload library — upload an image/file once here, then reuse
    its URL anywhere (blog cover, banner, offer image, etc.) instead of
    re-uploading the same file repeatedly across different admin forms.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(
        upload_to="media_library/%Y/%m/",
        validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp", "gif", "pdf"])],
        help_text="Images or PDFs only",
    )
    alt_text = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "media_assets"
        ordering = ["-created_at"]

    def __str__(self):
        return self.alt_text or self.file.name

    @property
    def file_size(self):
        try:
            return self.file.size
        except (ValueError, FileNotFoundError):
            return None

    @property
    def is_image(self):
        name = self.file.name.lower()
        return name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"))
