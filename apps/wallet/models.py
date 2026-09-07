import uuid

from django.conf import settings
from django.db import models


class WalletTransaction(models.Model):
    """
    Ledger-style customer wallet — balance is always the sum of these rows
    (same pattern as VendorTransaction/DeliveryTransaction), never a
    separately-stored counter that could drift out of sync.
    """

    class Type(models.TextChoices):
        CREDIT = "credit", "Credit"
        DEBIT = "debit", "Debit"

    class Reason(models.TextChoices):
        REFERRAL_BONUS = "referral_bonus", "Referral bonus"
        REFUND = "refund", "Order refund"
        CASHBACK = "cashback", "Cashback"
        ORDER_PAYMENT = "order_payment", "Used for order payment"
        ADMIN_ADJUSTMENT = "admin_adjustment", "Admin adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="wallet_transactions", on_delete=models.CASCADE)
    type = models.CharField(max_length=10, choices=Type.choices)
    reason = models.CharField(max_length=20, choices=Reason.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Always positive — type says direction")
    order_reference = models.CharField(max_length=30, blank=True)
    description = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "wallet_transactions"
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(check=models.Q(amount__gt=0), name="wallet_txn_amount_positive")]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        sign = "+" if self.type == self.Type.CREDIT else "-"
        return f"{self.user}: {sign}₹{self.amount} ({self.reason})"

    @property
    def signed_amount(self):
        return self.amount if self.type == self.Type.CREDIT else -self.amount


class Referral(models.Model):
    """
    One row per successful referral relationship. Created when the referred
    user signs up with a code; reward_credited flips True once their first
    delivered order triggers the bonus payout (see apps.wallet.services).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    referrer = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="referrals_given", on_delete=models.CASCADE)
    referred_user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name="referral_received", on_delete=models.CASCADE
    )
    reward_credited = models.BooleanField(default=False)
    reward_credited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "referrals"

    def __str__(self):
        return f"{self.referrer} referred {self.referred_user}"
