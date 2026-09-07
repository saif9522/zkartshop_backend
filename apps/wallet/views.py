from django.db.models import Sum
from rest_framework import permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.wallet.models import Referral, WalletTransaction
from apps.wallet.serializers import ReferralInfoSerializer, ReferralSerializer, WalletTransactionSerializer
from apps.wallet.services import get_wallet_balance


class WalletBalanceView(APIView):
    """Current spendable balance for the logged-in user (any role — not customer-only)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({"balance": get_wallet_balance(request.user)})


class WalletTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """The logged-in user's own wallet ledger."""

    serializer_class = WalletTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return WalletTransaction.objects.filter(user=self.request.user)


class ReferralInfoView(APIView):
    """My referral code + how many people I've referred + how much I've earned from it."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        referrals = Referral.objects.filter(referrer=request.user)
        total_earned = WalletTransaction.objects.filter(
            user=request.user, reason=WalletTransaction.Reason.REFERRAL_BONUS
        ).aggregate(t=Sum("amount"))["t"] or 0
        data = {
            "referral_code": request.user.referral_code,
            "total_referred": referrals.count(),
            "total_earned": total_earned,
        }
        return Response(ReferralInfoSerializer(data).data)


class MyReferralsViewSet(viewsets.ReadOnlyModelViewSet):
    """People I've referred, and whether their reward has been credited yet."""

    serializer_class = ReferralSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Referral.objects.filter(referrer=self.request.user).select_related("referred_user")
