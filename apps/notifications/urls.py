from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.notifications.views import (
    NotificationViewSet,
    PushSubscribeView,
    PushUnsubscribeView,
    VapidPublicKeyView,
)

router = DefaultRouter()
router.register("", NotificationViewSet, basename="notification")

urlpatterns = [
    path("push/vapid-key/", VapidPublicKeyView.as_view(), name="vapid-public-key"),
    path("push/subscribe/", PushSubscribeView.as_view(), name="push-subscribe"),
    path("push/unsubscribe/", PushUnsubscribeView.as_view(), name="push-unsubscribe"),
] + router.urls
