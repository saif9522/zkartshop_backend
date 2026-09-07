from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import OTP, Address, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["-date_joined"]
    list_display = ["phone", "full_name", "role", "is_phone_verified", "is_active", "date_joined"]
    list_filter = ["role", "is_active", "is_phone_verified"]
    search_fields = ["phone", "email", "full_name"]
    readonly_fields = ["id", "date_joined", "last_login"]
    fieldsets = (
        (None, {"fields": ("phone", "email", "password")}),
        ("Profile", {"fields": ("full_name", "avatar", "role")}),
        ("Verification", {"fields": ("is_phone_verified", "is_email_verified", "google_id")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("phone", "full_name", "role", "password1", "password2")}),
    )


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ["user", "label", "city", "pincode", "is_default"]
    list_filter = ["label", "city"]
    search_fields = ["user__phone", "address_line", "pincode"]


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ["phone", "purpose", "is_used", "attempts", "created_at", "expires_at"]
    list_filter = ["purpose", "is_used"]
    readonly_fields = ["code", "created_at"]
