import pytest

from conftest import auth

pytestmark = pytest.mark.django_db


@pytest.fixture
def ready_order(customer, customer_address, cart_with_product, vendor_owner):
    from apps.orders.services import checkout_cart, transition_order

    orders, _, _ = checkout_cart(customer, customer_address.id, "cod")
    order = orders[0]
    order = transition_order(order, "accepted", actor=vendor_owner, vendor_initiated=True)
    order = transition_order(order, "packing", actor=vendor_owner, vendor_initiated=True)
    order = transition_order(order, "ready", actor=vendor_owner, vendor_initiated=True)
    return order


class TestDeliveryClaim:
    def test_dashboard_active_orders_includes_claimed_not_yet_picked_up(self, api_client, delivery_owner, delivery_partner, ready_order):
        client = auth(api_client, delivery_owner)
        client.post(f"/api/v1/delivery/orders/{ready_order.id}/assign/")

        response = client.get("/api/v1/delivery/dashboard/")
        assert response.status_code == 200
        assert response.data["active_orders"] == 1

    def test_second_partner_cannot_claim_already_claimed_order(self, api_client, delivery_owner, delivery_partner, ready_order):
        from rest_framework.test import APIClient

        from apps.accounts.models import User
        from apps.delivery.models import DeliveryProfile

        client = auth(api_client, delivery_owner)
        client.post(f"/api/v1/delivery/orders/{ready_order.id}/assign/")

        other = User.objects.create_user(phone="+919444000001", password="x", role="delivery")
        DeliveryProfile.objects.create(user=other, vehicle_type="bike", status="approved", is_online=True)
        other_client = auth(APIClient(), other)
        response = other_client.post(f"/api/v1/delivery/orders/{ready_order.id}/assign/")
        assert response.status_code == 400


class TestDeliveryOTPFlow:
    def test_full_pickup_and_delivery_otp_flow(self, api_client, delivery_owner, delivery_partner, ready_order):
        from apps.delivery.models import DeliveryTransaction

        client = auth(api_client, delivery_owner)
        client.post(f"/api/v1/delivery/orders/{ready_order.id}/assign/")
        ready_order.refresh_from_db()

        bad = client.post(f"/api/v1/delivery/orders/{ready_order.id}/confirm-pickup/", {"otp": "0000"}, format="json")
        assert bad.status_code == 400

        good = client.post(
            f"/api/v1/delivery/orders/{ready_order.id}/confirm-pickup/", {"otp": ready_order.pickup_otp}, format="json"
        )
        assert good.status_code == 200

        client.post(f"/api/v1/delivery/orders/{ready_order.id}/start-delivery/")
        client.post(f"/api/v1/delivery/orders/{ready_order.id}/mark-nearby/")
        ready_order.refresh_from_db()

        delivered = client.post(
            f"/api/v1/delivery/orders/{ready_order.id}/confirm-delivery/", {"otp": ready_order.delivery_otp}, format="json"
        )
        assert delivered.status_code == 200
        ready_order.refresh_from_db()
        assert ready_order.status == "delivered"
        assert DeliveryTransaction.objects.filter(delivery_partner=delivery_owner).exists()  # commission was actually credited

    def test_delivered_today_counts_correctly(self, api_client, delivery_owner, delivery_partner, ready_order):
        """Regression test for the timezone bug: delivered_today must use IST, not UTC, 'today'."""
        client = auth(api_client, delivery_owner)
        client.post(f"/api/v1/delivery/orders/{ready_order.id}/assign/")
        ready_order.refresh_from_db()
        client.post(f"/api/v1/delivery/orders/{ready_order.id}/confirm-pickup/", {"otp": ready_order.pickup_otp}, format="json")
        client.post(f"/api/v1/delivery/orders/{ready_order.id}/start-delivery/")
        client.post(f"/api/v1/delivery/orders/{ready_order.id}/mark-nearby/")
        ready_order.refresh_from_db()
        client.post(f"/api/v1/delivery/orders/{ready_order.id}/confirm-delivery/", {"otp": ready_order.delivery_otp}, format="json")

        response = client.get("/api/v1/delivery/dashboard/")
        assert response.data["delivered_today"] == 1
        assert float(response.data["earnings"]["today"]) > 0
