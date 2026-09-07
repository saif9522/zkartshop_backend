import pytest

from conftest import auth

pytestmark = pytest.mark.django_db


class TestRecommendations:
    def test_similar_products_same_category_only(self, api_client, vendor, category, product):
        from apps.catalog.models import Category, Product

        Product.objects.create(vendor=vendor, category=category, name="Dal", unit="1kg", mrp="80", selling_price="70", stock_quantity=10)
        other_cat = Category.objects.create(name="Electronics")
        Product.objects.create(vendor=vendor, category=other_cat, name="Phone", unit="1pc", mrp="10000", selling_price="9500", stock_quantity=5)

        response = api_client.get(f"/api/v1/catalog/products/{product.slug}/similar/")
        assert response.status_code == 200
        names = [p["name"] for p in response.data]
        assert "Dal" in names
        assert "Phone" not in names

    def test_frequently_bought_together_from_real_orders(self, api_client, customer, customer_address, vendor, category, product):
        from apps.cart.models import Cart, CartItem
        from apps.catalog.models import Product
        from apps.orders.services import checkout_cart

        dal = Product.objects.create(vendor=vendor, category=category, name="Dal", unit="1kg", mrp="80", selling_price="70", stock_quantity=10)
        cart, _ = Cart.objects.get_or_create(user=customer)
        CartItem.objects.create(cart=cart, product=product, quantity=1)
        CartItem.objects.create(cart=cart, product=dal, quantity=1)
        checkout_cart(customer, customer_address.id, "cod")

        response = api_client.get(f"/api/v1/catalog/products/{product.slug}/frequently-bought-together/")
        assert response.status_code == 200
        assert any(p["name"] == "Dal" for p in response.data)


class TestProductOwnership:
    def test_vendor_cannot_edit_other_vendors_product(self, api_client, product):
        from apps.accounts.models import User
        from apps.vendors.models import Vendor

        other_owner = User.objects.create_user(phone="+919666000001", password="x", role="vendor")
        Vendor.objects.create(
            owner=other_owner, shop_name="Other Shop", category="grocery", status="approved",
            is_open=True, address_line="X", latitude=24.1, longitude=83.8,
        )
        client = auth(api_client, other_owner)
        response = client.patch(f"/api/v1/catalog/products/{product.slug}/", {"name": "Hacked"}, format="json")
        assert response.status_code == 404

    def test_vendor_can_add_image_to_own_product(self, api_client, vendor_owner, product):
        import base64

        from django.core.files.uploadedfile import SimpleUploadedFile

        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        client = auth(api_client, vendor_owner)
        response = client.post(
            f"/api/v1/catalog/products/{product.slug}/images/",
            {"image": SimpleUploadedFile("p.png", png, content_type="image/png"), "is_primary": True},
            format="multipart",
        )
        assert response.status_code == 201


class TestMediaUploadSecurity:
    def test_media_library_rejects_executable_file(self, api_client, admin_user):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client = auth(api_client, admin_user)
        bad_file = SimpleUploadedFile("malware.exe", b"fake", content_type="application/octet-stream")
        response = client.post("/api/v1/admin/media-library/", {"file": bad_file, "alt_text": "x"}, format="multipart")
        assert response.status_code == 400
