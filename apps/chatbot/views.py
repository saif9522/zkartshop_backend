from rest_framework import permissions, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chatbot.models import ChatConversation, ChatMessage
from apps.chatbot.serializers import ChatConversationSerializer, SendMessageSerializer
from apps.chatbot.services import ChatbotUnavailable, get_chat_reply


class ChatConversationViewSet(viewsets.ReadOnlyModelViewSet):
    """The logged-in customer's own chat history."""

    serializer_class = ChatConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatConversation.objects.filter(user=self.request.user).prefetch_related("messages")


class SendMessageView(APIView):
    """
    Send a message to the AI assistant. If conversation_id is omitted, a new
    conversation is started. Returns the assistant's reply plus the
    conversation id (so the frontend can continue the same thread).
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation_id = serializer.validated_data.get("conversation_id")
        user_message = serializer.validated_data["message"]

        if conversation_id:
            conversation = ChatConversation.objects.filter(id=conversation_id, user=request.user).first()
            if not conversation:
                raise ValidationError("Conversation not found.")
        else:
            conversation = ChatConversation.objects.create(user=request.user)

        ChatMessage.objects.create(conversation=conversation, role=ChatMessage.Role.USER, content=user_message)

        history = [
            {"role": m.role, "content": m.content}
            for m in conversation.messages.order_by("created_at")
        ]

        try:
            reply_text = get_chat_reply(request.user, history)
        except ChatbotUnavailable as exc:
            return Response({"detail": str(exc)}, status=503)
        except Exception:
            return Response(
                {"detail": "The assistant is temporarily unavailable — please try again in a moment."}, status=502
            )

        reply = ChatMessage.objects.create(conversation=conversation, role=ChatMessage.Role.ASSISTANT, content=reply_text)
        conversation.save(update_fields=["updated_at"])

        return Response(
            {
                "conversation_id": str(conversation.id),
                "reply": {"id": str(reply.id), "role": reply.role, "content": reply.content, "created_at": reply.created_at},
            }
        )
