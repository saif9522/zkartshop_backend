from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import OTP, Address, Role, User


def tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    if hasattr(user, "vendor_profile"):
        user.vendor_profile.__class__.objects.filter(pk=user.vendor_profile.pk).update(last_login_at=timezone.now())
    elif hasattr(user, "delivery_profile"):
        user.delivery_profile.__class__.objects.filter(pk=user.delivery_profile.pk).update(last_login_at=timezone.now())

    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", "phone", "email", "full_name", "role",
            "is_phone_verified", "is_email_verified", "avatar", "referral_code", "date_joined",
        ]
        read_only_fields = ["id", "role", "is_phone_verified", "is_email_verified", "referral_code", "date_joined"]


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id", "label", "address_line", "landmark", "city", "state",
            "pincode", "latitude", "longitude", "is_default",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        if validated_data.get("is_default"):
            Address.objects.filter(user=validated_data["user"]).update(is_default=False)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if validated_data.get("is_default"):
            Address.objects.filter(user=instance.user).exclude(pk=instance.pk).update(is_default=False)
        return super().update(instance, validated_data)


class SendOTPSerializer(serializers.Serializer):
    phone = serializers.CharField()
    purpose = serializers.ChoiceField(choices=OTP.Purpose.choices, default=OTP.Purpose.LOGIN)

    def create(self, validated_data):
        from apps.core.task_utils import safe_delay
        from apps.notifications.tasks import send_otp_sms_task

        otp = OTP.objects.create(phone=validated_data["phone"], purpose=validated_data["purpose"])
        if not safe_delay(send_otp_sms_task, str(otp.phone), otp.code):
            # Redis/Celery unreachable — fall back to a direct console print
            # so local dev keeps working without Redis running.
            print(f"[DEV - Celery unavailable] OTP for {otp.phone} ({otp.purpose}): {otp.code}")
        return otp


class ResetPasswordSerializer(serializers.Serializer):
    """Verifies a reset_password OTP, then sets a new password on the matching account."""

    phone = serializers.CharField()
    code = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        otp = (
            OTP.objects.filter(phone=attrs["phone"], purpose=OTP.Purpose.RESET_PASSWORD, is_used=False)
            .order_by("-created_at")
            .first()
        )
        if not otp:
            raise serializers.ValidationError("No pending reset code for this phone number.")
        if otp.attempts >= 5:
            raise serializers.ValidationError("Too many attempts. Request a new code.")

        otp.attempts += 1
        otp.save(update_fields=["attempts"])

        if not otp.is_valid(attrs["code"]):
            raise serializers.ValidationError("Invalid or expired code.")

        try:
            user = User.objects.get(phone=attrs["phone"])
        except User.DoesNotExist:
            raise serializers.ValidationError("No account found for this phone number.")

        attrs["otp"] = otp
        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        otp = self.validated_data["otp"]
        otp.is_used = True
        otp.save(update_fields=["is_used"])

        user = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class VerifyOTPSerializer(serializers.Serializer):
    phone = serializers.CharField()
    code = serializers.CharField(max_length=6)
    purpose = serializers.ChoiceField(choices=OTP.Purpose.choices, default=OTP.Purpose.LOGIN)
    role = serializers.ChoiceField(choices=Role.choices, default=Role.CUSTOMER, required=False)
    full_name = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, allow_blank=True, write_only=True, min_length=8)
    referral_code = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate_role(self, value):
        # Mirrors RegisterSerializer: only self-registrable roles may be set via OTP
        # signup. Admin/super-admin accounts must never be creatable by an
        # unauthenticated request that only proves control of a phone number.
        if value not in (Role.CUSTOMER, Role.VENDOR, Role.DELIVERY):
            raise serializers.ValidationError("Invalid self-registration role.")
        return value

    def validate(self, attrs):
        otp = (
            OTP.objects.filter(phone=attrs["phone"], purpose=attrs["purpose"], is_used=False)
            .order_by("-created_at")
            .first()
        )
        if not otp:
            raise serializers.ValidationError("No pending OTP for this phone number.")
        if otp.attempts >= 5:
            raise serializers.ValidationError("Too many attempts. Request a new OTP.")

        otp.attempts += 1
        otp.save(update_fields=["attempts"])

        if not otp.is_valid(attrs["code"]):
            raise serializers.ValidationError("Invalid or expired OTP.")

        attrs["otp"] = otp
        return attrs

    def save(self, **kwargs):
        otp = self.validated_data["otp"]
        otp.is_used = True
        otp.save(update_fields=["is_used"])

        user, created = User.objects.get_or_create(
            phone=self.validated_data["phone"],
            defaults={
                "role": self.validated_data.get("role", Role.CUSTOMER),
                "full_name": self.validated_data.get("full_name", ""),
                "is_phone_verified": True,
            },
        )
        if created and self.validated_data.get("password"):
            user.set_password(self.validated_data["password"])
            user.save(update_fields=["password"])
        if created and self.validated_data.get("referral_code"):
            from apps.wallet.services import process_referral_signup

            process_referral_signup(user, self.validated_data["referral_code"])
        if not created and not user.is_phone_verified:
            user.is_phone_verified = True
            user.save(update_fields=["is_phone_verified"])

        return user


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    referral_code = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["phone", "email", "full_name", "password", "role", "referral_code"]

    def validate_role(self, value):
        # Only customer/vendor/delivery may self-register; admins are created internally.
        if value not in (Role.CUSTOMER, Role.VENDOR, Role.DELIVERY):
            raise serializers.ValidationError("Invalid self-registration role.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        referral_code = validated_data.pop("referral_code", None)
        user = User.objects.create_user(password=password, **validated_data)
        if referral_code:
            from apps.wallet.services import process_referral_signup

            process_referral_signup(user, referral_code)
        if user.email:
            from apps.core.task_utils import safe_delay
            from apps.notifications.tasks import send_transactional_email_task

            safe_delay(
                send_transactional_email_task, user.email, "Welcome to zKart.shop!",
                f"Hi {user.full_name or 'there'},\n\nWelcome to zKart.shop — fast delivery, right to your door. "
                f"Your account is ready to go.\n\nHappy shopping!",
            )
        return user


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        from django.contrib.auth import authenticate

        user = authenticate(phone=attrs["phone"], password=attrs["password"])
        if not user:
            raise serializers.ValidationError("Invalid phone number or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account has been deactivated.")
        attrs["user"] = user
        return attrs


class GoogleLoginSerializer(serializers.Serializer):
    """
    Frontend obtains the Google ID token via Google Identity Services,
    sends it here. We verify it against Google's servers and log the user in.
    """

    id_token = serializers.CharField()

    def validate_id_token(self, value):
        from django.conf import settings
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token

        try:
            payload = google_id_token.verify_oauth2_token(
                value, google_requests.Request(), settings.GOOGLE_OAUTH_CLIENT_ID
            )
        except ValueError as exc:
            raise serializers.ValidationError("Invalid Google token.") from exc
        return payload

    def save(self, **kwargs):
        payload = self.validated_data["id_token"]
        user, _ = User.objects.get_or_create(
            google_id=payload["sub"],
            defaults={
                "phone": None,
                "email": payload.get("email"),
                "full_name": payload.get("name", ""),
                "is_email_verified": True,
                "role": Role.CUSTOMER,
            },
        )
        return user
