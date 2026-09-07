from rest_framework import mixins, permissions, viewsets

from apps.cms.models import BlogPost, ContactMessage, FAQ, FooterLink, Page
from apps.cms.serializers import (
    BlogPostDetailSerializer,
    BlogPostListSerializer,
    ContactMessageCreateSerializer,
    FAQSerializer,
    FooterLinkSerializer,
    PageSerializer,
)


class FAQViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = FAQ.objects.filter(is_active=True)
    serializer_class = FAQSerializer
    permission_classes = [permissions.AllowAny]


class PageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Page.objects.filter(is_active=True)
    serializer_class = PageSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"


class BlogPostViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BlogPost.objects.filter(is_published=True)
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"

    def get_serializer_class(self):
        return BlogPostDetailSerializer if self.action == "retrieve" else BlogPostListSerializer


class FooterLinkViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = FooterLink.objects.filter(is_active=True)
    serializer_class = FooterLinkSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class ContactMessageViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Public — anyone (logged in or not) can submit a contact message. No read access here."""

    queryset = ContactMessage.objects.none()
    serializer_class = ContactMessageCreateSerializer
    permission_classes = [permissions.AllowAny]
