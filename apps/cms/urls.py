from rest_framework.routers import DefaultRouter

from apps.cms.views import BlogPostViewSet, ContactMessageViewSet, FAQViewSet, FooterLinkViewSet, PageViewSet

router = DefaultRouter()
router.register("faqs", FAQViewSet, basename="faq")
router.register("pages", PageViewSet, basename="page")
router.register("blog", BlogPostViewSet, basename="blogpost")
router.register("footer-links", FooterLinkViewSet, basename="footerlink")
router.register("contact", ContactMessageViewSet, basename="contactmessage")

urlpatterns = router.urls
