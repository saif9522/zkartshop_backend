import pytest

from conftest import auth

pytestmark = pytest.mark.django_db


class TestGranularRBAC:
    def test_admin_without_permission_flag_is_blocked(self, api_client, admin_user, vendor):
        vendor.status = "pending"
        vendor.save()
        client = auth(api_client, admin_user)
        response = client.post(f"/api/v1/admin/vendors/{vendor.id}/approve/")
        assert response.status_code == 403

    def test_admin_with_permission_flag_is_allowed(self, api_client, admin_user, vendor):
        from apps.superadmin.models import StaffPermission

        vendor.status = "pending"
        vendor.save()
        StaffPermission.objects.create(user=admin_user, can_manage_vendors=True)
        client = auth(api_client, admin_user)
        response = client.post(f"/api/v1/admin/vendors/{vendor.id}/approve/")
        assert response.status_code == 200

    def test_regular_customer_cannot_access_admin_endpoints(self, api_client, customer):
        client = auth(api_client, customer)
        response = client.get("/api/v1/admin/vendors/")
        assert response.status_code == 403

    def test_otp_verify_cannot_grant_super_admin(self, api_client):
        from apps.accounts.models import OTP

        OTP.objects.create(phone="+919777000001", purpose="signup", code="1234")
        response = api_client.post(
            "/api/v1/auth/login/otp/verify/",
            {"phone": "+919777000001", "code": "1234", "purpose": "signup", "role": "super_admin"},
            format="json",
        )
        assert response.status_code == 400
