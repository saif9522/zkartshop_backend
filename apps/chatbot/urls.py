from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.chatbot.views import ChatConversationViewSet, SendMessageView

router = DefaultRouter()
router.register("conversations", ChatConversationViewSet, basename="chat-conversation")

urlpatterns = [
    path("message/", SendMessageView.as_view(), name="chat-send-message"),
] + router.urls
