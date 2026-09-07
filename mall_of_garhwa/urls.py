from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core.document_access import ServeDocumentView
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

schema_view = get_schema_view(
    openapi.Info(
        title="zKart.shop API",
        default_version="v1",
        description=(
            "REST API for zKart.shop — a quick-commerce marketplace. "
            "Covers auth, catalog, cart, orders, vendor/delivery/admin/super-admin "
            "panels, notifications, and reports. "
            "Authenticate with a JWT: click 'Authorize' and paste "
            "`Bearer <your access token>`."
        ),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/catalog/", include("apps.catalog.urls")),
    path("api/v1/cart/", include("apps.cart.urls")),
    path("api/v1/vendors/", include("apps.vendors.urls")),
    path("api/v1/inventory/", include("apps.inventory.urls")),
    path("api/v1/orders/", include("apps.orders.urls")),
    path("api/v1/delivery/", include("apps.delivery.urls")),
    path("api/v1/admin/", include("apps.adminpanel.urls")),
    path("api/v1/super-admin/", include("apps.superadmin.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    path("api/v1/reports/", include("apps.reports.urls")),
    path("api/v1/marketing/", include("apps.marketing.urls")),
    path("api/v1/cms/", include("apps.cms.urls")),
    path("api/v1/wallet/", include("apps.wallet.urls")),
    path("api/v1/documents/serve/", ServeDocumentView.as_view(), name="serve-document"),
    path("api/v1/chatbot/", include("apps.chatbot.urls")),
    # API docs
    path("swagger/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-swagger-ui"),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
    path("swagger.json", schema_view.without_ui(cache_timeout=0), name="schema-json"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
