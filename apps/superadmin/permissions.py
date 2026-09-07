from rest_framework.permissions import BasePermission

from apps.accounts.models import Role


class HasStaffPermission(BasePermission):
    """
    Base class — subclass and set `required_flag` to a StaffPermission
    boolean field name. super_admin always passes; admin needs the flag
    set True on their StaffPermission row (missing row = no permissions).
    """

    required_flag = None

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == Role.SUPER_ADMIN:
            return True
        if user.role != Role.ADMIN:
            return False

        from apps.superadmin.models import StaffPermission

        try:
            perms = user.staff_permission
        except StaffPermission.DoesNotExist:
            return False
        return getattr(perms, self.required_flag, False)


class CanManageVendors(HasStaffPermission):
    required_flag = "can_manage_vendors"


class CanManageDeliveryPartners(HasStaffPermission):
    required_flag = "can_manage_delivery_partners"


class CanManageOrders(HasStaffPermission):
    required_flag = "can_manage_orders"


class CanManageCoupons(HasStaffPermission):
    required_flag = "can_manage_coupons"


class CanManageCategories(HasStaffPermission):
    required_flag = "can_manage_categories"


class CanManageUsers(HasStaffPermission):
    required_flag = "can_manage_users"


class CanViewReports(HasStaffPermission):
    required_flag = "can_view_reports"
