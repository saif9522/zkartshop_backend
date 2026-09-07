from rest_framework import permissions, viewsets

from apps.marketing.models import Banner, Offer, Slider
from apps.marketing.serializers import BannerSerializer, OfferSerializer, SliderSerializer


class SliderViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Slider.objects.live()
    serializer_class = SliderSerializer
    permission_classes = [permissions.AllowAny]


class BannerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Banner.objects.live()
    serializer_class = BannerSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        position = self.request.query_params.get("position")
        return qs.filter(position=position) if position else qs


class OfferViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Offer.objects.live()
    serializer_class = OfferSerializer
    permission_classes = [permissions.AllowAny]
