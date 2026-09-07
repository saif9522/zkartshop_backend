from rest_framework.permissions import BasePermission

from apps.accounts.models import Role


class HasRole(BasePermission):
    """Base class — subclass and set `allowed_roles`."""

    allowed_roles: tuple = ()

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in self.allowed_roles
        )


class IsCustomer(HasRole):
    allowed_roles = (Role.CUSTOMER,)


class IsVendor(HasRole):
    allowed_roles = (Role.VENDOR,)


class IsDeliveryPartner(HasRole):
    allowed_roles = (Role.DELIVERY,)


class IsAdmin(HasRole):
    allowed_roles = (Role.ADMIN, Role.SUPER_ADMIN)


class IsSuperAdmin(HasRole):
    allowed_roles = (Role.SUPER_ADMIN,)


class IsOwnerOrAdmin(BasePermission):
    """Object-level: the request user owns the object, or is admin/super-admin."""

    def has_object_permission(self, request, view, obj):
        owner = getattr(obj, "user", obj)
        return owner == request.user or request.user.role in (Role.ADMIN, Role.SUPER_ADMIN)
