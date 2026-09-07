from django.contrib import admin

from apps.delivery.models import Attendance, DeliveryProfile, DeliveryTransaction


@admin.register(DeliveryProfile)
class DeliveryProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "vehicle_type", "vehicle_number", "status", "is_online"]
    list_filter = ["vehicle_type", "status", "is_online"]
    search_fields = ["user__phone", "vehicle_number", "license_number"]


@admin.register(DeliveryTransaction)
class DeliveryTransactionAdmin(admin.ModelAdmin):
    list_display = ["delivery_partner", "type", "amount", "order_reference", "created_at"]
    list_filter = ["type"]
    search_fields = ["delivery_partner__phone", "order_reference"]


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ["delivery_partner", "date", "check_in_time", "check_out_time", "hours_worked"]
    list_filter = ["date"]
    search_fields = ["delivery_partner__phone"]
