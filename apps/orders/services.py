import logging
import random
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Address
from apps.catalog.models import Product
from apps.inventory.models import StockMovement
from apps.inventory.services import record_stock_movement
from apps.orders.models import Coupon, ExtraCharge, Order, OrderItem, OrderStatusHistory
from apps.vendors.models import VendorTransaction

logger = logging.getLogger(__name__)


def applicable_extra_charges(subtotal, at_time=None):
    """
    Returns the list of admin-configured extra charges that apply to an order
    of this subtotal right now, as [{code, label, amount}]. Empty if the admin
    hasn't added/enabled any — so nothing shows until they do.
    """
    rows = []
    for charge in ExtraCharge.objects.filter(is_active=True):
        if not charge.applies_now(subtotal, at_time=at_time):
            continue
        amount = charge.compute_amount(subtotal)
        if amount <= 0:
            continue
        rows.append({"code": charge.code, "label": charge.label, "amount": amount})
    return rows


class InsufficientStockError(ValidationError):
    pass


def validate_coupon(code, subtotal):
    """Returns (coupon, discount_amount) or raises ValidationError."""
    try:
        coupon = Coupon.objects.get(code__iexact=code)
    except Coupon.DoesNotExist as exc:
        raise ValidationError("Invalid coupon code.") from exc

    if not coupon.is_valid_now():
        raise ValidationError("This coupon has expired or is no longer active.")

    discount = coupon.calculate_discount(subtotal)
    if discount <= 0:
        raise ValidationError(f"Cart total must be at least ₹{coupon.min_order_value} to use this coupon.")

    return coupon, discount


def _validate_payment_method(payment_method, subtotal):
    """
    If admin has configured this payment method (disabled it, or set a
    minimum order value), enforce that. No config row = method is allowed
    with no restrictions (so this stays backward-compatible if admin never
    touches the Payment Methods settings at all).
    """
    from apps.orders.models import PaymentMethodConfig

    config = PaymentMethodConfig.objects.filter(code=payment_method).first()
    if not config:
        return
    if not config.is_enabled:
        raise ValidationError(f"{config.label or payment_method} is currently unavailable. Please choose another payment method.")
    if config.min_order_value and subtotal < config.min_order_value:
        raise ValidationError(
            f"{config.label or payment_method} requires a minimum order of ₹{config.min_order_value}."
        )


def estimate_delivery(subtotal, vendor, address):
    """Public wrapper around _delivery_charge_for — lets the cart/checkout UI preview distance + charge before placing the order."""
    from apps.delivery.services import haversine_km

    distance_km = None
    if vendor.latitude is not None and vendor.longitude is not None and address.latitude is not None and address.longitude is not None:
        distance_km = round(haversine_km(vendor.latitude, vendor.longitude, address.latitude, address.longitude), 1)

    try:
        charge = _delivery_charge_for(subtotal, vendor, address)
        error = None
    except ValidationError as exc:
        charge = None
        error = str(exc.detail[0]) if isinstance(exc.detail, list) else str(exc.detail)

    return {"vendor_id": str(vendor.id), "vendor_name": vendor.shop_name, "distance_km": distance_km, "delivery_charge": charge, "extra_charges": applicable_extra_charges(subtotal), "error": error}


def _delivery_charge_for(subtotal, vendor, address):
    """
    Base charge covers the first `delivery_free_km`; every km beyond that
    adds `delivery_per_km_charge`. City-level overrides (if the vendor is
    linked to a managed City) replace the base charge and free-delivery
    threshold, but distance-based pricing beyond the free radius still
    applies on top — a city admin sets the *starting* price, not the whole
    formula.
    """
    from apps.delivery.services import haversine_km
    from apps.superadmin.models import PlatformSettings

    platform = PlatformSettings.load()
    threshold = platform.default_free_delivery_threshold
    base_charge = platform.default_delivery_charge

    city = getattr(vendor, "city_ref", None)
    if city:
        if city.free_delivery_threshold is not None:
            threshold = city.free_delivery_threshold
        if city.delivery_charge is not None:
            base_charge = city.delivery_charge

    if subtotal >= threshold:
        return 0

    if vendor.latitude is None or vendor.longitude is None or address.latitude is None or address.longitude is None:
        # Missing coordinates (shouldn't normally happen — both are required at
        # onboarding/address-creation) — fall back to the flat base charge.
        return base_charge

    distance_km = haversine_km(vendor.latitude, vendor.longitude, address.latitude, address.longitude)
    if distance_km > platform.max_delivery_radius_km:
        raise ValidationError(
            f"{vendor.shop_name} is {distance_km:.1f} km away — outside our {platform.max_delivery_radius_km} km delivery range for this address."
        )

    extra_km = max(0, distance_km - float(platform.delivery_free_km))
    charge = float(base_charge) + extra_km * float(platform.delivery_per_km_charge)
    return Decimal(str(round(charge, 2)))


@transaction.atomic
def checkout_cart(user, address_id, payment_method, coupon_code=None):
    """
    Converts the user's cart into one Order per vendor. Locks and decrements
    stock for every line item, applies a coupon (split proportionally across
    vendor sub-orders by their share of the combined subtotal), and — for
    Razorpay payments — creates a single Razorpay Order covering the combined
    total so the customer pays once even if the cart spans several shops.

    Returns (orders, combined_grand_total, razorpay_order_payload | None).
    """
    from apps.cart.models import Cart

    try:
        cart = Cart.objects.select_related("user").get(user=user)
    except Cart.DoesNotExist as exc:
        raise ValidationError("Your cart is empty.") from exc

    items = list(cart.items.select_related("product", "product__vendor"))
    if not items:
        raise ValidationError("Your cart is empty.")

    try:
        address = Address.objects.get(id=address_id, user=user)
    except Address.DoesNotExist as exc:
        raise ValidationError("Delivery address not found.") from exc

    # Lock the actual product rows so two concurrent checkouts can't both
    # succeed against the same last unit of stock.
    product_ids = [item.product_id for item in items]
    locked_products = {p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids)}

    by_vendor = defaultdict(list)
    for item in items:
        product = locked_products[item.product_id]
        if item.quantity > product.stock_quantity:
            raise InsufficientStockError(f"Only {product.stock_quantity} of '{product.name}' left in stock.")
        by_vendor[product.vendor_id].append((item, product))

    combined_subtotal = sum(item.product.selling_price * item.quantity for item in items)
    _validate_payment_method(payment_method, combined_subtotal)

    coupon = None
    total_discount = 0
    if coupon_code:
        coupon, total_discount = validate_coupon(coupon_code, combined_subtotal)

    orders = []
    for vendor_id, vendor_items in by_vendor.items():
        vendor_subtotal = sum(product.selling_price * item.quantity for item, product in vendor_items)
        # This vendor's proportional share of the coupon discount.
        vendor_discount = (
            round(total_discount * (vendor_subtotal / combined_subtotal), 2) if combined_subtotal else 0
        )
        delivery_charge = _delivery_charge_for(vendor_subtotal, vendor_items[0][1].vendor, address)
        extra_charges = applicable_extra_charges(vendor_subtotal)
        extra_charges_total = sum((row["amount"] for row in extra_charges), Decimal("0"))
        grand_total = vendor_subtotal - vendor_discount + delivery_charge + extra_charges_total

        order = Order.objects.create(
            customer=user,
            vendor_id=vendor_id,
            delivery_address=address,
            payment_method=payment_method,
            subtotal=vendor_subtotal,
            delivery_charge=delivery_charge,
            discount_amount=vendor_discount,
            extra_charges_total=extra_charges_total,
            extra_charges_breakdown=[
                {"code": r["code"], "label": r["label"], "amount": str(r["amount"])} for r in extra_charges
            ],
            coupon_code=coupon.code if coupon else "",
            grand_total=grand_total,
            delivery_otp=f"{random.randint(0, 9999):04d}",
            pickup_otp=f"{random.randint(0, 9999):04d}",
        )
        OrderStatusHistory.objects.create(order=order, from_status="", to_status=Order.Status.PLACED, changed_by=user)

        for item, product in vendor_items:
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                unit=product.unit,
                price=product.selling_price,
                quantity=item.quantity,
            )
            product.stock_quantity -= item.quantity
            product.save(update_fields=["stock_quantity"])
            record_stock_movement(
                product, StockMovement.MovementType.SALE, -item.quantity,
                reference=order.order_number, actor=user,
            )

        orders.append(order)

    if coupon:
        coupon.used_count += 1
        coupon.save(update_fields=["used_count"])

    combined_grand_total = sum(o.grand_total for o in orders)

    razorpay_payload = None
    if payment_method == Order.PaymentMethod.RAZORPAY:
        razorpay_payload = create_razorpay_order(combined_grand_total, orders)
    elif payment_method == Order.PaymentMethod.WALLET:
        from apps.wallet.models import WalletTransaction
        from apps.wallet.services import debit_wallet

        order_numbers = ", ".join(o.order_number for o in orders)
        debit_wallet(
            user, combined_grand_total, WalletTransaction.Reason.ORDER_PAYMENT,
            order_reference=order_numbers, description=f"Payment for order(s) {order_numbers}",
        )
        Order.objects.filter(id__in=[o.id for o in orders]).update(payment_status=Order.PaymentStatus.PAID)
        for o in orders:
            o.payment_status = Order.PaymentStatus.PAID

    cart.items.all().delete()

    for order in orders:
        _notify_order_placed(order)

    return orders, combined_grand_total, razorpay_payload


def create_razorpay_order(amount, orders):
    """
    Creates one Razorpay Order for the combined checkout total and tags it
    onto every vendor sub-order so payment verification can mark them all
    paid together. Docs: https://razorpay.com/docs/api/orders/
    """
    import razorpay

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    receipt = orders[0].order_number
    try:
        rp_order = client.order.create({
            "amount": int(amount * 100),  # paise
            "currency": "INR",
            "receipt": receipt,
            "notes": {"order_numbers": ",".join(o.order_number for o in orders)},
        })
    except Exception as exc:  # razorpay.errors.BadRequestError etc.
        logger.error("Razorpay order creation failed: %s", exc)
        raise ValidationError("Could not initiate payment. Please try again.") from exc

    Order.objects.filter(id__in=[o.id for o in orders]).update(razorpay_order_id=rp_order["id"])
    return {"razorpay_order_id": rp_order["id"], "amount": rp_order["amount"], "currency": rp_order["currency"], "key": settings.RAZORPAY_KEY_ID}


def verify_razorpay_payment(razorpay_order_id, razorpay_payment_id, razorpay_signature, user):
    """Verifies the payment signature and marks every order under this Razorpay order as paid."""
    import razorpay
    from razorpay.errors import SignatureVerificationError

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
    except SignatureVerificationError as exc:
        raise ValidationError("Payment verification failed.") from exc

    orders = Order.objects.filter(razorpay_order_id=razorpay_order_id, customer=user)
    if not orders.exists():
        raise ValidationError("No matching order found for this payment.")

    orders.update(payment_status=Order.PaymentStatus.PAID, razorpay_payment_id=razorpay_payment_id)
    return list(orders)


def transition_order(order, new_status, *, actor, vendor_initiated, reason=""):
    if not order.can_transition_to(new_status, vendor_initiated=vendor_initiated):
        raise ValidationError(f"Cannot move an order from '{order.status}' to '{new_status}'.")

    old_status = order.status
    order.status = new_status

    if new_status == Order.Status.ACCEPTED:
        order.accepted_at = timezone.now()
    elif new_status == Order.Status.CANCELLED:
        order.cancelled_at = timezone.now()
        order.cancel_reason = reason
        _restock_order(order)
        _refund_payment_if_needed(order)
    elif new_status == Order.Status.DELIVERED:
        order.delivered_at = timezone.now()
        _settle_vendor_earnings(order)
        if order.delivery_partner_id:
            _settle_delivery_earnings(order)

    order.save()
    OrderStatusHistory.objects.create(order=order, from_status=old_status, to_status=new_status, changed_by=actor)
    _notify_status_change(order)

    if new_status == Order.Status.DELIVERED:
        from apps.wallet.services import credit_referral_reward_if_eligible

        credit_referral_reward_if_eligible(order)

    return order


def _restock_order(order):
    for item in order.items.select_related("product"):
        if item.product:
            item.product.stock_quantity += item.quantity
            item.product.save(update_fields=["stock_quantity"])
            record_stock_movement(
                item.product, StockMovement.MovementType.RETURN, item.quantity,
                reference=order.order_number, notes="Order cancelled",
            )


def _refund_payment_if_needed(order):
    """
    Cancelling a PAID order must actually return the customer's money —
    for Razorpay that's a real refund call; for wallet it's an instant
    credit back. COD orders are unaffected (nothing was collected yet).
    """
    if order.payment_status != Order.PaymentStatus.PAID:
        return

    if order.payment_method == Order.PaymentMethod.WALLET:
        from apps.wallet.models import WalletTransaction
        from apps.wallet.services import credit_wallet

        credit_wallet(
            order.customer, order.grand_total, WalletTransaction.Reason.REFUND,
            order_reference=order.order_number, description=f"Refund for cancelled order {order.order_number}",
        )
        order.payment_status = Order.PaymentStatus.REFUNDED
        order.save(update_fields=["payment_status"])
        return

    if order.payment_method != Order.PaymentMethod.RAZORPAY:
        return

    import razorpay

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    try:
        client.payment.refund(
            order.razorpay_payment_id,
            {
                "amount": int(order.grand_total * 100),  # paise; full refund
                "speed": "optimum",
                "notes": {"order_number": order.order_number, "reason": "Order cancelled"},
            },
        )
    except Exception as exc:  # razorpay.errors.* — network issue, already-refunded, etc.
        logger.error("Razorpay refund failed for order %s: %s", order.order_number, exc)
        # Leave payment_status as PAID (not REFUNDED) so this doesn't silently
        # look resolved — it'll surface in admin/reports for manual follow-up.
        return

    order.payment_status = Order.PaymentStatus.REFUNDED
    order.save(update_fields=["payment_status"])


def _settle_vendor_earnings(order):
    """Credits the vendor (net of commission) once an order is delivered."""
    commission_rate = order.vendor.commission_percent / 100
    commission_amount = round(order.subtotal * commission_rate, 2)
    net_amount = order.subtotal - commission_amount

    VendorTransaction.objects.create(
        vendor=order.vendor, type=VendorTransaction.Type.CREDIT, amount=net_amount,
        order_reference=order.order_number, description=f"Order {order.order_number} settlement",
    )
    VendorTransaction.objects.create(
        vendor=order.vendor, type=VendorTransaction.Type.COMMISSION, amount=-commission_amount,
        order_reference=order.order_number,
        description=f"Platform commission ({order.vendor.commission_percent}%) on {order.order_number}",
    )


def _settle_delivery_earnings(order):
    """Credits the delivery partner a flat per-order payout once delivered."""
    from apps.delivery.models import DeliveryTransaction

    DeliveryTransaction.objects.create(
        delivery_partner_id=order.delivery_partner_id,
        type=DeliveryTransaction.Type.DELIVERY_EARNING,
        amount=settings.DELIVERY_PARTNER_PAYOUT_PER_ORDER,
        order_reference=order.order_number,
        description=f"Delivery payout for {order.order_number}",
    )


def _notify_order_placed(order):
    from apps.accounts.models import Role, User
    from apps.core.task_utils import safe_delay
    from apps.notifications.models import Notification
    from apps.notifications.services import notify_user, notify_users
    from apps.notifications.tasks import (
        send_transactional_email_task,
        send_transactional_sms_task,
        send_whatsapp_message_task,
    )

    order_placed_message = f"Your zKart.shop order {order.order_number} worth ₹{order.grand_total} has been placed!"
    safe_delay(send_transactional_sms_task, str(order.customer.phone), order_placed_message)
    safe_delay(send_whatsapp_message_task, str(order.customer.phone), order_placed_message)
    if order.customer.email:
        safe_delay(
            send_transactional_email_task, order.customer.email, f"Order confirmed — {order.order_number}",
            f"Hi {order.customer.full_name or 'there'},\n\n"
            f"Your order {order.order_number} from {order.vendor.shop_name} has been placed successfully.\n\n"
            f"Total: ₹{order.grand_total}\nPayment: {order.get_payment_method_display()}\n\n"
            f"We'll notify you as it's prepared and on its way!",
        )

    notify_user(
        order.vendor.owner, Notification.Type.ORDER,
        f"New order — {order.order_number}",
        f"₹{order.grand_total} · {order.items.count()} item(s). Accept it to start preparing.",
        {"order_id": str(order.id)},
    )
    notify_users(
        User.objects.filter(role__in=[Role.ADMIN, Role.SUPER_ADMIN], is_active=True),
        Notification.Type.ORDER,
        f"New order placed — {order.order_number}",
        f"{order.vendor.shop_name} · ₹{order.grand_total}",
        {"order_id": str(order.id)},
    )


def _notify_status_change(order):
    from apps.accounts.models import Role, User
    from apps.core.realtime import broadcast_to_order
    from apps.core.task_utils import safe_delay
    from apps.delivery.models import DeliveryProfile
    from apps.notifications.models import Notification
    from apps.notifications.services import notify_users
    from apps.notifications.tasks import (
        send_transactional_email_task,
        send_transactional_sms_task,
        send_whatsapp_message_task,
    )

    broadcast_to_order(
        str(order.id), "status_update", {"status": order.status, "order_number": order.order_number}
    )

    if order.status == Order.Status.READY:
        partners = User.objects.filter(
            role=Role.DELIVERY, delivery_profile__status=DeliveryProfile.Status.APPROVED,
            delivery_profile__is_online=True,
        )
        notify_users(
            partners, Notification.Type.DELIVERY,
            "New delivery available",
            f"{order.vendor.shop_name} · {order.order_number} · ₹{order.grand_total}",
            {"order_id": str(order.id)},
        )

    messages = {
        Order.Status.ACCEPTED: f"Order {order.order_number} accepted by {order.vendor.shop_name}.",
        Order.Status.OUT_FOR_DELIVERY: f"Order {order.order_number} is out for delivery!",
        Order.Status.DELIVERED: f"Order {order.order_number} delivered. Enjoy!",
        Order.Status.CANCELLED: f"Order {order.order_number} was cancelled.",
    }
    message = messages.get(order.status)
    if message:
        safe_delay(send_transactional_sms_task, str(order.customer.phone), message)
        safe_delay(send_whatsapp_message_task, str(order.customer.phone), message)

    if order.status == Order.Status.DELIVERED and order.customer.email:
        safe_delay(
            send_transactional_email_task, order.customer.email, f"Delivered — {order.order_number}",
            f"Hi {order.customer.full_name or 'there'},\n\n"
            f"Your order {order.order_number} from {order.vendor.shop_name} has been delivered. Enjoy!\n\n"
            f"Thank you for shopping with zKart.shop.",
        )
