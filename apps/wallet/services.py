import logging

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from apps.wallet.models import Referral, WalletTransaction

logger = logging.getLogger(__name__)


def get_wallet_balance(user):
    """The actual spendable balance — credits minus debits."""
    credits = WalletTransaction.objects.filter(user=user, type=WalletTransaction.Type.CREDIT).aggregate(
        t=Sum("amount")
    )["t"] or 0
    debits = WalletTransaction.objects.filter(user=user, type=WalletTransaction.Type.DEBIT).aggregate(
        t=Sum("amount")
    )["t"] or 0
    return credits - debits


def credit_wallet(user, amount, reason, order_reference="", description="", created_by=None):
    if amount <= 0:
        return None
    return WalletTransaction.objects.create(
        user=user, type=WalletTransaction.Type.CREDIT, reason=reason, amount=amount,
        order_reference=order_reference, description=description, created_by=created_by,
    )


def debit_wallet(user, amount, reason, order_reference="", description="", created_by=None):
    """Raises ValidationError if the wallet doesn't have enough balance — never lets it go negative."""
    if amount <= 0:
        return None
    with transaction.atomic():
        # Lock this user's wallet rows so two concurrent debits (e.g. two
        # checkout attempts) can't both pass the balance check.
        WalletTransaction.objects.select_for_update().filter(user=user)
        balance = get_wallet_balance(user)
        if balance < amount:
            raise ValidationError(f"Insufficient wallet balance. Available: ₹{balance}, needed: ₹{amount}.")
        return WalletTransaction.objects.create(
            user=user, type=WalletTransaction.Type.DEBIT, reason=reason, amount=amount,
            order_reference=order_reference, description=description, created_by=created_by,
        )


def process_referral_signup(new_user, referral_code):
    """
    Called right after a new customer account is created with a referral
    code. Just links the relationship — the reward is credited later, only
    once the referred user's first order is actually delivered (so a
    signup-and-vanish doesn't cost anything).
    """
    if not referral_code:
        return None
    from apps.accounts.models import User

    referrer = User.objects.filter(referral_code__iexact=referral_code).exclude(id=new_user.id).first()
    if not referrer:
        return None

    new_user.referred_by = referrer
    new_user.save(update_fields=["referred_by"])
    return Referral.objects.create(referrer=referrer, referred_user=new_user)


def credit_referral_reward_if_eligible(order):
    """
    Call this when an order is marked DELIVERED. If this is the customer's
    FIRST delivered order and they were referred by someone, credit both
    sides' wallets — once only (reward_credited guards against double-firing
    if this order is somehow re-processed).
    """
    from apps.orders.models import Order
    from apps.superadmin.models import PlatformSettings

    customer = order.customer
    try:
        referral = customer.referral_received
    except Referral.DoesNotExist:
        return
    if referral.reward_credited:
        return

    delivered_count = Order.objects.filter(customer=customer, status=Order.Status.DELIVERED).count()
    if delivered_count != 1:
        # Not their first delivered order (or somehow zero) — only reward the very first.
        return

    from django.utils import timezone

    settings_row = PlatformSettings.load()
    credit_wallet(
        referral.referrer, settings_row.referral_bonus_referrer, WalletTransaction.Reason.REFERRAL_BONUS,
        order_reference=order.order_number, description=f"Referral bonus — {customer.full_name or customer.phone} placed their first order",
    )
    credit_wallet(
        customer, settings_row.referral_bonus_referred, WalletTransaction.Reason.REFERRAL_BONUS,
        order_reference=order.order_number, description="Welcome bonus for using a referral code",
    )
    referral.reward_credited = True
    referral.reward_credited_at = timezone.now()
    referral.save(update_fields=["reward_credited", "reward_credited_at"])
    logger.info("Referral reward credited for referral %s (order %s)", referral.id, order.order_number)
