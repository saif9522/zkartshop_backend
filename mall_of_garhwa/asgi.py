import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mall_of_garhwa.settings.production")

django_asgi_app = get_asgi_application()

# Imported after Django apps are loaded to avoid AppRegistryNotReady errors.
from apps.core.channels_auth import JWTAuthMiddleware  # noqa: E402
from apps.core.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
