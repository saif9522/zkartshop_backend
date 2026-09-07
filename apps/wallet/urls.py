from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.wallet.views import MyReferralsViewSet, ReferralInfoView, WalletBalanceView, WalletTransactionViewSet

router = DefaultRouter()
router.register("transactions", WalletTransactionViewSet, basename="wallet-transaction")
router.register("my-referrals", MyReferralsViewSet, basename="my-referral")

urlpatterns = [
    path("balance/", WalletBalanceView.as_view(), name="wallet-balance"),
    path("referral-info/", ReferralInfoView.as_view(), name="referral-info"),
] + router.urls
