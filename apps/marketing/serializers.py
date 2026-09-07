from rest_framework import serializers

from apps.marketing.models import Banner, Offer, Slider


class SliderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Slider
        fields = ["id", "title", "subtitle", "image", "link_url", "display_order"]


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = ["id", "title", "image", "link_url", "position", "display_order"]


class OfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = ["id", "title", "description", "image", "discount_label", "link_url", "display_order"]
