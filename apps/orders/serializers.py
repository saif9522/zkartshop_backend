from rest_framework import serializers

from apps.orders.models import Order, OrderItem, OrderStatusHistory, PaymentMethodConfig


class CheckoutSerializer(serializers.Serializer):
    address_id = serializers.UUIDField()
    payment_method = serializers.ChoiceField(choices=Order.PaymentMethod.choices)
    coupon_code = serializers.CharField(required=False, allow_blank=True)


class PaymentVerifySerializer(serializers.Serializer):
    razorpay_order_id = serializers.CharField()
    razorpay_payment_id = serializers.CharField()
    razorpay_signature = serializers.CharField()


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "unit", "price", "quantity", "subtotal"]


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ["from_status", "to_status", "changed_at"]


class OrderListSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.shop_name", read_only=True)
    item_count = serializers.IntegerField(source="items.count", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "vendor_name", "status", "payment_method",
            "payment_status", "grand_total", "item_count", "placed_at",
        ]


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    vendor_name = serializers.CharField(source="vendor.shop_name", read_only=True)
    delivery_address_text = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "vendor", "vendor_name", "status", "payment_method",
            "payment_status", "subtotal", "delivery_charge", "discount_amount",
            "extra_charges_total", "extra_charges_breakdown",
            "coupon_code", "grand_total", "delivery_address_text", "delivery_otp", "items",
            "status_history", "placed_at", "accepted_at", "delivered_at", "cancelled_at",
        ]

    def get_delivery_address_text(self, obj):
        addr = obj.delivery_address
        return f"{addr.address_line}, {addr.city} - {addr.pincode}"


class VendorOrderListSerializer(OrderListSerializer):
    """Adds the customer's name — a vendor needs to know who an order is for."""

    customer_name = serializers.CharField(source="customer.full_name", read_only=True)

    class Meta(OrderListSerializer.Meta):
        fields = OrderListSerializer.Meta.fields + ["customer_name"]


class VendorOrderDetailSerializer(OrderDetailSerializer):
    """
    Adds the customer's name+phone (packing slip / contact if needed) and
    pickup_otp — the vendor must read this OTP out to the delivery partner
    when they arrive to collect the order; none of this is shown to the
    customer-facing OrderDetailSerializer.
    """

    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)

    class Meta(OrderDetailSerializer.Meta):
        fields = OrderDetailSerializer.Meta.fields + ["customer_name", "customer_phone", "pickup_otp"]


class CancelOrderSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class AdvanceStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[
        (Order.Status.PACKING, Order.Status.PACKING.label),
        (Order.Status.READY, Order.Status.READY.label),
    ])


class PaymentMethodConfigSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()

    class Meta:
        model = PaymentMethodConfig
        fields = ["code", "label", "extra_fee", "min_order_value"]

    def get_label(self, obj):
        return obj.label or obj.get_code_display()
