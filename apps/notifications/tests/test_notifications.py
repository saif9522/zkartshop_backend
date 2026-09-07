import pytest

from conftest import auth

pytestmark = pytest.mark.django_db


class TestInAppNotifications:
    def test_notify_user_creates_notification_and_never_raises(self, customer):
        from apps.notifications.models import Notification
        from apps.notifications.services import notify_user

        result = notify_user(customer, Notification.Type.SYSTEM, "Test", "Body text")
        assert result is not None
        assert Notification.objects.filter(user=customer, title="Test").exists()

    def test_unread_count_and_mark_read(self, api_client, customer):
        from apps.notifications.models import Notification

        Notification.objects.create(user=customer, type=Notification.Type.SYSTEM, title="A", body="a")
        Notification.objects.create(user=customer, type=Notification.Type.SYSTEM, title="B", body="b")

        client = auth(api_client, customer)
        response = client.get("/api/v1/notifications/unread_count/")
        assert response.data["unread_count"] == 2

        response = client.post("/api/v1/notifications/mark-all-read/")
        assert response.data["marked_read"] == 2

        response = client.get("/api/v1/notifications/unread_count/")
        assert response.data["unread_count"] == 0

    def test_new_order_notifies_vendor(self, customer, customer_address, cart_with_product, vendor_owner):
        from apps.notifications.models import Notification
        from apps.orders.services import checkout_cart

        checkout_cart(customer, customer_address.id, "cod")
        assert Notification.objects.filter(user=vendor_owner, type=Notification.Type.ORDER).exists()


class TestPushSubscription:
    def test_subscribe_and_vapid_key_endpoint(self, api_client, customer):
        response = api_client.get("/api/v1/notifications/push/vapid-key/")
        assert response.status_code == 200

        client = auth(api_client, customer)
        response = client.post(
            "/api/v1/notifications/push/subscribe/",
            {"endpoint": "https://fcm.googleapis.com/fcm/send/test", "p256dh_key": "k1", "auth_key": "k2"},
            format="json",
        )
        assert response.status_code == 201

        from apps.notifications.models import PushSubscription

        assert PushSubscription.objects.filter(user=customer).exists()
