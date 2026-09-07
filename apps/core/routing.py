from django.urls import re_path

from apps.delivery.consumers import OrderTrackingConsumer

websocket_urlpatterns = [
    re_path(r"^ws/orders/(?P<order_id>[0-9a-fA-F-]+)/track/$", OrderTrackingConsumer.as_asgi()),
]
