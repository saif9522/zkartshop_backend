from django.contrib import admin

from apps.superadmin.models import BackupLog, City, PlatformSettings, StaffPermission, Warehouse


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ["name", "state", "delivery_charge", "free_delivery_threshold", "is_active"]
    search_fields = ["name", "state"]


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "is_active"]
    list_filter = ["city", "is_active"]


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ["default_commission_percent", "default_delivery_charge", "maintenance_mode", "updated_at"]

    def has_add_permission(self, request):
        return not PlatformSettings.objects.exists()


@admin.register(StaffPermission)
class StaffPermissionAdmin(admin.ModelAdmin):
    list_display = ["user", "can_manage_vendors", "can_manage_orders", "can_manage_coupons", "can_manage_users"]
    search_fields = ["user__phone"]


@admin.register(BackupLog)
class BackupLogAdmin(admin.ModelAdmin):
    list_display = ["filename", "status", "size_bytes", "started_at", "finished_at"]
    list_filter = ["status"]
    readonly_fields = ["started_at"]
