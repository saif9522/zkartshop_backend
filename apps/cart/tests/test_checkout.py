import pytest

from conftest import auth

pytestmark = pytest.mark.django_db


class TestAddToCart:
    def test_add_to_cart_respects_existing_quantity(self, api_client, customer, product):
        client = auth(api_client, customer)
        client.post("/api/v1/cart/items/", {"product_id": str(product.id), "quantity": 3}, format="json")

        product.stock_quantity = 5
        product.save()

        response = client.post("/api/v1/cart/items/", {"product_id": str(product.id), "quantity": 4}, format="json")
        assert response.status_code == 400

    def test_cannot_add_out_of_stock_product(self, api_client, customer, product):
        product.stock_quantity = 0
        product.save()
        client = auth(api_client, customer)
        response = client.post("/api/v1/cart/items/", {"product_id": str(product.id), "quantity": 1}, format="json")
        assert response.status_code == 400


class TestCheckout:
    def test_cod_checkout_creates_order_and_clears_cart(self, api_client, customer, customer_address, cart_with_product):
        from apps.orders.models import Order

        client = auth(api_client, customer)
        response = client.post(
            "/api/v1/orders/checkout/", {"address_id": str(customer_address.id), "payment_method": "cod"}, format="json"
        )
        assert response.status_code == 201
        assert Order.objects.filter(customer=customer).exists()
        assert cart_with_product.items.count() == 0

    def test_checkout_decrements_stock(self, api_client, customer, customer_address, cart_with_product, product):
        client = auth(api_client, customer)
        starting_stock = product.stock_quantity
        client.post("/api/v1/orders/checkout/", {"address_id": str(customer_address.id), "payment_method": "cod"}, format="json")
        product.refresh_from_db()
        assert product.stock_quantity == starting_stock - 1

    def test_wallet_checkout_debits_balance(self, api_client, customer, customer_address, cart_with_product):
        from apps.wallet.models import WalletTransaction
        from apps.wallet.services import credit_wallet, get_wallet_balance

        credit_wallet(customer, 500, WalletTransaction.Reason.CASHBACK)
        client = auth(api_client, customer)

        response = client.post(
            "/api/v1/orders/checkout/", {"address_id": str(customer_address.id), "payment_method": "wallet"}, format="json"
        )
        assert response.status_code == 201
        assert get_wallet_balance(customer) < 500

    def test_wallet_checkout_blocked_when_insufficient(self, api_client, customer, customer_address, cart_with_product):
        from apps.orders.models import Order

        client = auth(api_client, customer)
        response = client.post(
            "/api/v1/orders/checkout/", {"address_id": str(customer_address.id), "payment_method": "wallet"}, format="json"
        )
        assert response.status_code == 400
        assert not Order.objects.filter(customer=customer).exists()
        assert cart_with_product.items.count() == 1

    def test_checkout_with_empty_cart_rejected(self, api_client, customer, customer_address):
        client = auth(api_client, customer)
        response = client.post(
            "/api/v1/orders/checkout/", {"address_id": str(customer_address.id), "payment_method": "cod"}, format="json"
        )
        assert response.status_code == 400
