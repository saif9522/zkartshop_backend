import pytest

from conftest import auth

pytestmark = pytest.mark.django_db


class TestReferralReward:
    def test_reward_credited_only_after_first_delivered_order(
        self, api_client, customer, customer_address, cart_with_product, vendor_owner, delivery_owner, delivery_partner
    ):
        from apps.accounts.models import User
        from apps.orders.services import checkout_cart, transition_order
        from apps.wallet.models import Referral
        from apps.wallet.services import get_wallet_balance, process_referral_signup

        referrer = User.objects.create_user(phone="+919555000001", password="x", role="customer")
        process_referral_signup(customer, referrer.referral_code)

        referrer_balance_before = get_wallet_balance(referrer)
        referred_balance_before = get_wallet_balance(customer)

        orders, _, _ = checkout_cart(customer, customer_address.id, "cod")
        order = orders[0]

        referral = Referral.objects.get(referred_user=customer)
        assert referral.reward_credited is False

        order = transition_order(order, "accepted", actor=vendor_owner, vendor_initiated=True)
        order = transition_order(order, "packing", actor=vendor_owner, vendor_initiated=True)
        order = transition_order(order, "ready", actor=vendor_owner, vendor_initiated=True)

        from apps.delivery.services import assign_order, confirm_pickup, confirm_delivery, mark_nearby, start_delivery

        order = assign_order(order.id, delivery_owner)
        order = confirm_pickup(order, delivery_owner, order.pickup_otp)
        order = start_delivery(order, delivery_owner)
        order = mark_nearby(order, delivery_owner)
        order = confirm_delivery(order, delivery_owner, order.delivery_otp)

        referral.refresh_from_db()
        assert referral.reward_credited is True
        assert get_wallet_balance(referrer) > referrer_balance_before
        assert get_wallet_balance(customer) > referred_balance_before


class TestWalletBalance:
    def test_debit_never_goes_negative(self, customer):
        from rest_framework.exceptions import ValidationError

        from apps.wallet.models import WalletTransaction
        from apps.wallet.services import credit_wallet, debit_wallet

        credit_wallet(customer, 100, WalletTransaction.Reason.CASHBACK)
        with pytest.raises(ValidationError):
            debit_wallet(customer, 150, WalletTransaction.Reason.ORDER_PAYMENT)

    def test_balance_is_credits_minus_debits(self, customer):
        from apps.wallet.models import WalletTransaction
        from apps.wallet.services import credit_wallet, debit_wallet, get_wallet_balance

        credit_wallet(customer, 200, WalletTransaction.Reason.CASHBACK)
        debit_wallet(customer, 50, WalletTransaction.Reason.ORDER_PAYMENT)
        assert get_wallet_balance(customer) == 150


class TestWalletAPI:
    def test_customer_can_view_own_balance(self, api_client, customer):
        client = auth(api_client, customer)
        response = client.get("/api/v1/wallet/balance/")
        assert response.status_code == 200
        assert "balance" in response.data
