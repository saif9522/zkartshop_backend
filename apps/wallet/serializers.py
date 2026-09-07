from rest_framework import serializers

from apps.wallet.models import Referral, WalletTransaction


class WalletTransactionSerializer(serializers.ModelSerializer):
    signed_amount = serializers.ReadOnlyField()

    class Meta:
        model = WalletTransaction
        fields = ["id", "type", "reason", "amount", "signed_amount", "order_reference", "description", "created_at"]


class ReferralInfoSerializer(serializers.Serializer):
    referral_code = serializers.CharField()
    total_referred = serializers.IntegerField()
    total_earned = serializers.DecimalField(max_digits=10, decimal_places=2)


class ReferralSerializer(serializers.ModelSerializer):
    referred_user_name = serializers.CharField(source="referred_user.full_name", read_only=True)
    referred_user_phone = serializers.CharField(source="referred_user.phone", read_only=True)

    class Meta:
        model = Referral
        fields = ["id", "referred_user_name", "referred_user_phone", "reward_credited", "reward_credited_at", "created_at"]
