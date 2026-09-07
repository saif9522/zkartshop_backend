from rest_framework import serializers

from apps.notifications.models import Notification, PushSubscription


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "type", "title", "body", "data", "is_read", "created_at"]
        read_only_fields = fields


class PushSubscriptionSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=500)
    p256dh_key = serializers.CharField(max_length=255)
    auth_key = serializers.CharField(max_length=255)
