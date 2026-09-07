import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def customer(db):
    from apps.accounts.models import User

    return User.objects.create_user(phone="+919000000001", password="TestPass123", role="customer", email="customer@example.com", full_name="Test Customer")


@pytest.fixture
def customer_address(db, customer):
    from apps.accounts.models import Address

    return Address.objects.create(
        user=customer, address_line="123 Test Street", city="Garhwa", pincode="822114",
        latitude=24.1553, longitude=83.8099, is_default=True,
    )


@pytest.fixture
def vendor_owner(db):
    from apps.accounts.models import User

    return User.objects.create_user(phone="+919000000002", password="TestPass123", role="vendor")


@pytest.fixture
def vendor(db, vendor_owner):
    from apps.vendors.models import Vendor

    return Vendor.objects.create(
        owner=vendor_owner, shop_name="Test Kirana", category="grocery", status="approved",
        is_open=True, address_line="Shop 1, Main Bazaar", latitude=24.16, longitude=83.81,
    )


@pytest.fixture
def category(db):
    from apps.catalog.models import Category

    return Category.objects.create(name="Groceries")


@pytest.fixture
def product(db, vendor, category):
    from apps.catalog.models import Product

    return Product.objects.create(
        vendor=vendor, category=category, name="Rice 5kg", unit="5 kg",
        mrp="400", selling_price="380", stock_quantity=50,
    )


@pytest.fixture
def delivery_owner(db):
    from apps.accounts.models import User

    return User.objects.create_user(phone="+919000000003", password="TestPass123", role="delivery")


@pytest.fixture
def delivery_partner(db, delivery_owner):
    from apps.delivery.models import DeliveryProfile

    return DeliveryProfile.objects.create(
        user=delivery_owner, vehicle_type="bike", status="approved", is_online=True,
    )


@pytest.fixture
def admin_user(db):
    from apps.accounts.models import User

    return User.objects.create_user(phone="+919000000004", password="TestPass123", role="admin")


@pytest.fixture
def super_admin_user(db):
    from apps.accounts.models import User

    return User.objects.create_user(phone="+919000000005", password="TestPass123", role="super_admin", is_staff=True, is_superuser=True)


@pytest.fixture
def cart_with_product(db, customer, product):
    from apps.cart.models import Cart, CartItem

    cart, _ = Cart.objects.get_or_create(user=customer)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    return cart


def auth(api_client, user):
    """Attach a JWT for `user` to `api_client` and return the client for chaining."""
    from rest_framework_simplejwt.tokens import RefreshToken

    token = RefreshToken.for_user(user).access_token
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client
