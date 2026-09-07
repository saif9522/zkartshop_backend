from decimal import Decimal

from rest_framework import serializers

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductAttribute, ProductImage, ProductVariant, Review
from apps.cms.models import BlogPost, ContactMessage, FAQ, FooterLink, MediaAsset, Page
from apps.core.document_access import SignedDocumentFieldsMixin
from apps.marketing.models import Banner, Campaign, CampaignExternalContact, CampaignRecipient, Offer, Slider
from apps.delivery.models import DeliveryProfile
from apps.orders.models import Coupon, ExtraCharge, PaymentMethodConfig
from apps.wallet.models import WalletTransaction
from apps.vendors.models import Vendor


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", "phone", "email", "full_name", "role", "is_active",
            "is_phone_verified", "is_email_verified", "date_joined",
        ]
        read_only_fields = ["id", "phone", "role", "date_joined"]


class AdminVendorSerializer(SignedDocumentFieldsMixin, serializers.ModelSerializer):
    owner_phone = serializers.CharField(source="owner.phone", read_only=True)
    owner_name = serializers.CharField(source="owner.full_name", read_only=True)
    owner_email = serializers.CharField(source="owner.email", read_only=True)
    product_count = serializers.IntegerField(source="products.count", read_only=True)

    document_field_names = [
        "gst_certificate", "pan_card", "aadhaar_card", "shop_document", "business_registration_document",
        "fssai_license_document", "cancelled_cheque", "shop_front_photo", "shop_interior_photo", "owner_photo",
    ]

    class Meta:
        model = Vendor
        fields = [
            "id", "shop_name", "business_name", "category", "owner_phone", "owner_name", "owner_email",
            "whatsapp_number",
            "gst_number", "pan_number", "business_registration_number", "shop_license_number",
            "fssai_license_number", "business_type", "years_in_business",
            "bank_account_holder_name", "bank_name", "bank_account_number", "bank_ifsc_code", "upi_id",
            "gst_certificate", "pan_card", "aadhaar_card", "shop_document", "business_registration_document",
            "fssai_license_document", "cancelled_cheque", "shop_front_photo", "shop_interior_photo", "owner_photo",
            "commission_percent", "status", "verification_status",
            "address_line", "city", "state", "pincode", "country", "latitude", "longitude", "is_open",
            "product_count", "created_at", "last_login_at",
        ]
        read_only_fields = ["id", "owner_phone", "owner_name", "owner_email", "product_count", "created_at", "last_login_at"]


class AdminCreateVendorSerializer(serializers.Serializer):
    """Lets admin/super-admin add a vendor directly (skips the self-serve apply-and-approve flow)."""

    phone = serializers.CharField()
    full_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    shop_name = serializers.CharField(max_length=150)
    category = serializers.CharField(max_length=30)
    gst_number = serializers.CharField(max_length=15, required=False, allow_blank=True)
    address_line = serializers.CharField(max_length=255)
    city = serializers.CharField(max_length=100, default="Garhwa")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)


class AdminVendorCommissionSerializer(serializers.Serializer):
    commission_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100"))


class AdminDeliveryProfileSerializer(SignedDocumentFieldsMixin, serializers.ModelSerializer):
    owner_phone = serializers.CharField(source="user.phone", read_only=True)
    owner_name = serializers.CharField(source="user.full_name", read_only=True)
    owner_email = serializers.CharField(source="user.email", read_only=True)

    document_field_names = [
        "aadhaar_front_image", "aadhaar_back_image", "license_front_image", "license_back_image",
        "vehicle_rc_image", "vehicle_insurance_image", "pan_card_image", "passport_photo", "selfie_photo",
    ]

    class Meta:
        model = DeliveryProfile
        fields = [
            "id", "owner_phone", "owner_name", "owner_email", "whatsapp_number", "date_of_birth", "gender",
            "current_address", "permanent_address", "city", "state", "pincode", "country",
            "vehicle_type", "vehicle_number", "vehicle_rc_number", "insurance_number", "insurance_expiry_date",
            "aadhaar_number", "license_number", "pan_number",
            "aadhaar_front_image", "aadhaar_back_image", "license_front_image", "license_back_image",
            "vehicle_rc_image", "vehicle_insurance_image", "pan_card_image", "passport_photo", "selfie_photo",
            "status", "verification_status", "is_online", "rating_avg", "rating_count",
            "created_at", "last_login_at",
        ]
        read_only_fields = fields


class AdminCouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = [
            "id", "code", "discount_type", "discount_value", "max_discount",
            "min_order_value", "valid_from", "valid_to", "usage_limit",
            "used_count", "is_active",
        ]
        read_only_fields = ["id", "used_count"]

    def validate_code(self, value):
        return value.upper()


class AdminCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent", "icon", "display_order", "is_active"]
        read_only_fields = ["id"]


class AdminBrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name", "slug", "logo", "is_active"]
        read_only_fields = ["id"]


class AdminReviewSerializer(serializers.ModelSerializer):
    """Moderation view — admin can approve/unapprove or delete, never author a review."""

    product_name = serializers.CharField(source="product.name", read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)

    class Meta:
        model = Review
        fields = [
            "id", "product", "product_name", "customer_name", "customer_phone",
            "rating", "comment", "is_approved", "created_at",
        ]
        read_only_fields = ["id", "product", "rating", "comment", "created_at"]


class AdminSliderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Slider
        fields = [
            "id", "title", "subtitle", "image", "link_url",
            "display_order", "is_active", "valid_from", "valid_to", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class AdminBannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = [
            "id", "title", "image", "link_url", "position",
            "display_order", "is_active", "valid_from", "valid_to", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class AdminOfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = [
            "id", "title", "description", "image", "discount_label", "link_url",
            "display_order", "is_active", "valid_from", "valid_to", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class AdminFAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ["id", "question", "answer", "display_order", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class AdminPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ["id", "title", "slug", "content", "is_active", "updated_at", "created_at"]
        read_only_fields = ["id", "updated_at", "created_at"]


class AdminBlogPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogPost
        fields = [
            "id", "title", "slug", "excerpt", "content", "cover_image",
            "is_published", "published_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "published_at", "created_at", "updated_at"]


class AdminFooterLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = FooterLink
        fields = ["id", "section", "label", "url", "display_order", "is_active"]
        read_only_fields = ["id"]


class AdminContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ["id", "name", "email", "phone", "subject", "message", "status", "created_at"]
        read_only_fields = ["id", "name", "email", "phone", "subject", "message", "created_at"]


class AdminMediaAssetSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name", read_only=True, default=None)
    file_size = serializers.ReadOnlyField()
    is_image = serializers.ReadOnlyField()

    class Meta:
        model = MediaAsset
        fields = ["id", "file", "alt_text", "uploaded_by_name", "file_size", "is_image", "created_at"]
        read_only_fields = ["id", "created_at"]


class AdminProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "is_primary", "display_order"]
        read_only_fields = ["id"]


class AdminProductAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAttribute
        fields = ["id", "name", "value", "display_order"]
        read_only_fields = ["id"]


class AdminProductVariantSerializer(serializers.ModelSerializer):
    in_stock = serializers.ReadOnlyField()

    class Meta:
        model = ProductVariant
        fields = [
            "id", "name", "sku", "mrp", "selling_price",
            "stock_quantity", "is_available", "display_order", "in_stock",
        ]
        read_only_fields = ["id"]


class AdminProductSerializer(serializers.ModelSerializer):
    """
    Full product read/write for admin & super-admin: unlike the vendor-facing
    ProductWriteSerializer, `vendor` is a writable field here so staff can
    add/edit products for *any* shop on the platform, not just their own.
    """

    vendor_name = serializers.CharField(source="vendor.shop_name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    images = AdminProductImageSerializer(many=True, read_only=True)
    discount_percent = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = [
            "id", "vendor", "vendor_name", "category", "category_name", "brand",
            "name", "slug", "description", "unit", "mrp", "selling_price", "sku",
            "barcode", "stock_quantity", "is_available", "is_featured",
            "nutrition_info", "tags", "rating_avg", "rating_count",
            "discount_percent", "images", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "slug", "rating_avg", "rating_count", "created_at", "updated_at"]

    def validate(self, attrs):
        mrp = attrs.get("mrp", getattr(self.instance, "mrp", None))
        selling_price = attrs.get("selling_price", getattr(self.instance, "selling_price", None))
        if mrp is not None and selling_price is not None and selling_price > mrp:
            raise serializers.ValidationError("Selling price cannot exceed MRP.")
        return attrs


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class BroadcastNotificationSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["customer", "vendor", "delivery", "all"])
    title = serializers.CharField(max_length=100)
    message = serializers.CharField(max_length=500)


class AdminPaymentMethodConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethodConfig
        fields = ["id", "code", "label", "is_enabled", "extra_fee", "min_order_value", "display_order"]
        read_only_fields = ["id"]


class AdminExtraChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtraCharge
        fields = [
            "id", "code", "label", "charge_type", "amount", "max_charge",
            "min_order_value", "active_from_hour", "active_to_hour",
            "is_active", "display_order", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        for field in ("active_from_hour", "active_to_hour"):
            hour = attrs.get(field)
            if hour is not None and not (0 <= hour <= 23):
                raise serializers.ValidationError({field: "Hour must be between 0 and 23."})
        from_h = attrs.get("active_from_hour")
        to_h = attrs.get("active_to_hour")
        if (from_h is None) != (to_h is None):
            raise serializers.ValidationError(
                "Set both start and end hour for a time window, or leave both blank for 'any time'."
            )
        return attrs


class AdminWalletTransactionSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_phone = serializers.CharField(source="user.phone", read_only=True)

    class Meta:
        model = WalletTransaction
        fields = [
            "id", "user", "user_name", "user_phone", "type", "reason", "amount",
            "order_reference", "description", "created_at",
        ]
        read_only_fields = ["id", "reason", "created_at"]


class AdminCampaignSerializer(serializers.ModelSerializer):
    channels = serializers.ReadOnlyField()
    audience_city_name = serializers.CharField(source="audience_city.name", read_only=True, default=None)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)
    selected_customer_count = serializers.IntegerField(source="selected_customers.count", read_only=True)
    external_contact_count = serializers.IntegerField(source="external_contacts.count", read_only=True)

    class Meta:
        model = Campaign
        fields = [
            "id", "name", "is_ai_generated", "send_email", "send_sms", "send_whatsapp", "post_facebook", "post_instagram",
            "channels", "audience", "audience_city", "audience_city_name", "selected_customers",
            "selected_customer_count", "external_contact_count", "subject", "message", "image",
            "link_url", "scheduled_at", "status", "total_recipients", "sent_count", "failed_count",
            "facebook_post_id", "facebook_error", "instagram_post_id", "instagram_error",
            "created_by_name", "created_at", "sent_at",
        ]
        read_only_fields = [
            "id", "is_ai_generated", "status", "total_recipients", "sent_count", "failed_count",
            "facebook_post_id", "facebook_error", "instagram_post_id", "instagram_error",
            "created_at", "sent_at",
        ]
        extra_kwargs = {"selected_customers": {"write_only": True, "required": False}}

    def validate(self, attrs):
        channels = [
            attrs.get("send_email", getattr(self.instance, "send_email", False)),
            attrs.get("send_sms", getattr(self.instance, "send_sms", False)),
            attrs.get("send_whatsapp", getattr(self.instance, "send_whatsapp", False)),
            attrs.get("post_facebook", getattr(self.instance, "post_facebook", False)),
            attrs.get("post_instagram", getattr(self.instance, "post_instagram", False)),
        ]
        if not any(channels):
            raise serializers.ValidationError("Select at least one channel.")
        return attrs


class CampaignExternalContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignExternalContact
        fields = ["id", "name", "email", "phone", "email_status", "whatsapp_status"]
        read_only_fields = ["id", "email_status", "whatsapp_status"]

    def validate(self, attrs):
        if not attrs.get("email") and not attrs.get("phone"):
            raise serializers.ValidationError("Provide at least an email or a phone number.")
        return attrs


class SimpleCustomerSerializer(serializers.Serializer):
    """Lightweight — used for the individual-recipient picker list."""

    id = serializers.UUIDField()
    full_name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.CharField(allow_null=True)


class CampaignRecipientSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_phone = serializers.CharField(source="user.phone", read_only=True)

    class Meta:
        model = CampaignRecipient
        fields = ["id", "user_name", "user_phone", "channel", "status", "error", "sent_at"]
