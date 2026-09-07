from rest_framework import serializers

from apps.cms.models import BlogPost, ContactMessage, FAQ, FooterLink, Page


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ["id", "question", "answer", "display_order"]


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ["id", "title", "slug", "content", "updated_at"]


class BlogPostListSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogPost
        fields = ["id", "title", "slug", "excerpt", "cover_image", "published_at"]


class BlogPostDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogPost
        fields = ["id", "title", "slug", "excerpt", "content", "cover_image", "published_at"]


class FooterLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = FooterLink
        fields = ["id", "section", "label", "url", "display_order"]


class ContactMessageCreateSerializer(serializers.ModelSerializer):
    """Public-facing — anyone can submit, only these 5 fields are settable."""

    class Meta:
        model = ContactMessage
        fields = ["id", "name", "email", "phone", "subject", "message"]
        read_only_fields = ["id"]
