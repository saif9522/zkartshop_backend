import pytest

from apps.accounts.models import OTP, User

pytestmark = pytest.mark.django_db


class TestRegistration:
    def test_password_registration_creates_active_account(self, api_client):
        response = api_client.post(
            "/api/v1/auth/register/",
            {"phone": "+919111111111", "password": "SecurePass1", "full_name": "New User", "role": "customer"},
            format="json",
        )
        assert response.status_code == 201
        user = User.objects.get(phone="+919111111111")
        assert user.role == "customer"
        assert user.check_password("SecurePass1")
        assert user.referral_code  # auto-generated

    def test_cannot_self_register_as_admin(self, api_client):
        """A known privilege-escalation vector — self-registration must reject admin/super_admin roles."""
        response = api_client.post(
            "/api/v1/auth/register/",
            {"phone": "+919111111112", "password": "SecurePass1", "full_name": "Sneaky", "role": "admin"},
            format="json",
        )
        assert response.status_code == 400
        assert not User.objects.filter(phone="+919111111112").exists()

    def test_referral_code_links_referrer(self, api_client, customer):
        response = api_client.post(
            "/api/v1/auth/register/",
            {
                "phone": "+919111111113", "password": "SecurePass1", "full_name": "Referred User",
                "role": "customer", "referral_code": customer.referral_code,
            },
            format="json",
        )
        assert response.status_code == 201
        new_user = User.objects.get(phone="+919111111113")
        assert new_user.referred_by_id == customer.id


class TestOTPLogin:
    def test_otp_signup_creates_verified_account_with_working_password(self, api_client):
        OTP.objects.create(phone="+919222222221", purpose="signup", code="4321")
        response = api_client.post(
            "/api/v1/auth/login/otp/verify/",
            {
                "phone": "+919222222221", "code": "4321", "purpose": "signup",
                "role": "customer", "full_name": "OTP User", "password": "MyPassword1",
            },
            format="json",
        )
        assert response.status_code == 200
        user = User.objects.get(phone="+919222222221")
        assert user.is_phone_verified is True
        assert user.check_password("MyPassword1")

        # And that password should actually work for a future plain login.
        login_response = api_client.post("/api/v1/auth/login/", {"phone": "+919222222221", "password": "MyPassword1"})
        assert login_response.status_code == 200

    def test_otp_verify_rejects_privileged_role(self, api_client):
        OTP.objects.create(phone="+919222222222", purpose="signup", code="1234")
        response = api_client.post(
            "/api/v1/auth/login/otp/verify/",
            {"phone": "+919222222222", "code": "1234", "purpose": "signup", "role": "super_admin"},
            format="json",
        )
        assert response.status_code == 400

    def test_wrong_otp_code_rejected(self, api_client):
        OTP.objects.create(phone="+919222222223", purpose="signup", code="1234")
        response = api_client.post(
            "/api/v1/auth/login/otp/verify/",
            {"phone": "+919222222223", "code": "9999", "purpose": "signup", "role": "customer"},
            format="json",
        )
        assert response.status_code == 400
        assert not User.objects.filter(phone="+919222222223").exists()


class TestInactiveAccount:
    def test_deactivated_user_cannot_login(self, api_client, customer):
        customer.is_active = False
        customer.save()
        response = api_client.post("/api/v1/auth/login/", {"phone": str(customer.phone), "password": "TestPass123"})
        assert response.status_code == 400
