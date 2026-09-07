import pytest

from conftest import auth

pytestmark = pytest.mark.django_db


@pytest.fixture
def placed_order(customer, customer_address, cart_with_product):
    from apps.orders.services import checkout_cart

    orders, _, _ = checkout_cart(customer, customer_address.id, "cod")
    return orders[0]


class TestOrderLifecycle:
    def test_vendor_can_accept_own_order(self, api_client, vendor_owner, placed_order):
        client = auth(api_client, vendor_owner)
        response = client.post(f"/api/v1/orders/vendor/{placed_order.id}/accept/")
        assert response.status_code == 200
        placed_order.refresh_from_db()
        assert placed_order.status == "accepted"

    def test_other_vendor_cannot_touch_order(self, api_client, placed_order):
        from apps.accounts.models import User
        from apps.vendors.models import Vendor

        other_owner = User.objects.create_user(phone="+919333000001", password="x", role="vendor")
        Vendor.objects.create(
            owner=other_owner, shop_name="Other Shop", category="grocery", status="approved",
            is_open=True, address_line="X", latitude=24.1, longitude=83.8,
        )
        client = auth(api_client, other_owner)
        response = client.post(f"/api/v1/orders/vendor/{placed_order.id}/accept/")
        assert response.status_code == 404

    def test_customer_sees_own_delivery_otp(self, api_client, customer, placed_order):
        client = auth(api_client, customer)
        response = client.get(f"/api/v1/orders/{placed_order.id}/")
        assert response.status_code == 200
        assert response.data["delivery_otp"] == placed_order.delivery_otp
        assert len(placed_order.delivery_otp) == 4

    def test_vendor_sees_customer_name_and_pickup_otp(self, api_client, vendor_owner, placed_order):
        client = auth(api_client, vendor_owner)
        response = client.get(f"/api/v1/orders/vendor/{placed_order.id}/")
        assert response.status_code == 200
        assert response.data["customer_name"] == placed_order.customer.full_name
        assert response.data["pickup_otp"] == placed_order.pickup_otp

    def test_customer_order_detail_never_exposes_pickup_otp(self, api_client, customer, placed_order):
        client = auth(api_client, customer)
        response = client.get(f"/api/v1/orders/{placed_order.id}/")
        assert "pickup_otp" not in response.data


class TestCancelAndRefund:
    def test_wallet_paid_order_refunds_to_wallet_on_cancel(self, api_client, customer, customer_address, cart_with_product):
        from apps.orders.services import checkout_cart, transition_order
        from apps.wallet.models import WalletTransaction
        from apps.wallet.services import credit_wallet, get_wallet_balance

        credit_wallet(customer, 500, WalletTransaction.Reason.CASHBACK)
        orders, total, _ = checkout_cart(customer, customer_address.id, "wallet")
        order = orders[0]
        balance_after_payment = get_wallet_balance(customer)

        transition_order(order, "cancelled", actor=customer, vendor_initiated=False, reason="Changed my mind")
        order.refresh_from_db()

        assert order.payment_status == "refunded"
        assert get_wallet_balance(customer) == balance_after_payment + order.grand_total


class TestNotOnboardedVendorGuards:
    def test_profile_404s_cleanly(self, api_client, vendor_owner):
        client = auth(api_client, vendor_owner)
        response = client.get("/api/v1/vendors/profile/")
        assert response.status_code == 404

    def test_product_create_400s_cleanly(self, api_client, vendor_owner, category):
        client = auth(api_client, vendor_owner)
        response = client.post(
            "/api/v1/catalog/products/",
            {"category": str(category.id), "name": "Test", "unit": "1kg", "mrp": "10", "selling_price": "10", "stock_quantity": 1},
            format="json",
        )
        assert response.status_code == 400
