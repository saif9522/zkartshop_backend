from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.superadmin.views import (
    APIMonitoringView,
    AuditLogView,
    BackupListView,
    CityViewSet,
    CreateAdminView,
    PlatformSettingsView,
    StaffPermissionViewSet,
    TriggerBackupView,
    WarehouseViewSet,
)

router = DefaultRouter()
router.register("cities", CityViewSet, basename="city")
router.register("warehouses", WarehouseViewSet, basename="warehouse")
router.register("staff-permissions", StaffPermissionViewSet, basename="staff-permission")

urlpatterns = [
    path("settings/", PlatformSettingsView.as_view(), name="platform-settings"),
    path("staff/create-admin/", CreateAdminView.as_view(), name="create-admin"),
    path("logs/", AuditLogView.as_view(), name="audit-logs"),
    path("backups/trigger/", TriggerBackupView.as_view(), name="trigger-backup"),
    path("backups/", BackupListView.as_view(), name="backup-list"),
    path("monitoring/", APIMonitoringView.as_view(), name="api-monitoring"),
    path("", include(router.urls)),
]
