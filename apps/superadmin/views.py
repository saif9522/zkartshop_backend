from django.db.models import Count
from django.utils import timezone
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, User
from apps.accounts.permissions import IsSuperAdmin
from apps.core.models import AuditLog
from apps.superadmin.models import BackupLog, City, PlatformSettings, StaffPermission, Warehouse
from apps.superadmin.serializers import (
    AuditLogSerializer,
    CitySerializer,
    CreateAdminSerializer,
    PlatformSettingsSerializer,
    StaffPermissionSerializer,
    WarehouseSerializer,
)


class CityViewSet(viewsets.ModelViewSet):
    queryset = City.objects.all()
    serializer_class = CitySerializer
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]


class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.select_related("city")
    serializer_class = WarehouseSerializer
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]


class PlatformSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = PlatformSettingsSerializer
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get_object(self):
        return PlatformSettings.load()


class StaffPermissionViewSet(viewsets.ModelViewSet):
    """Manage RBAC flags for existing admin-role users."""

    queryset = StaffPermission.objects.select_related("user")
    serializer_class = StaffPermissionSerializer
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]
    http_method_names = ["get", "patch", "head", "options"]


class CreateAdminView(APIView):
    """Creates a new admin-role staff account with an initial RBAC permission set — super admin only."""

    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def post(self, request):
        serializer = CreateAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if User.objects.filter(phone=data["phone"]).exists():
            return Response({"detail": "A user with this phone already exists."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            phone=data["phone"], password=data["password"], full_name=data["full_name"],
            role=Role.ADMIN, is_phone_verified=True,
        )
        perms = StaffPermission.objects.create(
            user=user,
            department=data.get("department", StaffPermission.Department.CUSTOM),
            can_manage_vendors=data["can_manage_vendors"],
            can_manage_delivery_partners=data["can_manage_delivery_partners"],
            can_manage_orders=data["can_manage_orders"],
            can_manage_coupons=data["can_manage_coupons"],
            can_manage_categories=data["can_manage_categories"],
            can_manage_users=data["can_manage_users"],
            can_view_reports=data["can_view_reports"],
        )
        # If a department was chosen, its preset overrides the individual flags.
        perms.apply_department_preset()
        perms.save()
        return Response(StaffPermissionSerializer(perms).data, status=status.HTTP_201_CREATED)


class AuditLogView(generics.ListAPIView):
    """Every non-GET API call, platform-wide — who did what, when."""

    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user").order_by("-created_at")
        params = self.request.query_params
        if params.get("user"):
            qs = qs.filter(user_id=params["user"])
        if params.get("method"):
            qs = qs.filter(method=params["method"].upper())
        if params.get("path_contains"):
            qs = qs.filter(path__icontains=params["path_contains"])
        return qs


class TriggerBackupView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def post(self, request):
        from apps.core.task_utils import safe_delay
        from apps.superadmin.tasks import run_database_backup

        log = BackupLog.objects.create(triggered_by=request.user)
        if not safe_delay(run_database_backup, str(log.id)):
            log.status = BackupLog.Status.FAILED
            log.error_message = "Background job queue (Redis/Celery) is unreachable."
            log.save(update_fields=["status", "error_message"])
            return Response(
                {"detail": "Background job queue (Redis/Celery) is unreachable right now. Is Redis running?"},
                status=503,
            )
        return Response({"detail": "Backup started.", "backup_id": log.id}, status=status.HTTP_202_ACCEPTED)


class BackupListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        logs = BackupLog.objects.all()[:50]
        return Response([
            {
                "id": log.id, "filename": log.filename, "size_bytes": log.size_bytes,
                "status": log.status, "error_message": log.error_message,
                "started_at": log.started_at, "finished_at": log.finished_at,
            }
            for log in logs
        ])


class APIMonitoringView(APIView):
    """Lightweight request-volume and error-rate view, built from the audit log."""

    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        today = timezone.localdate()
        last_24h = timezone.now() - timezone.timedelta(hours=24)

        recent = AuditLog.objects.filter(created_at__gte=last_24h)
        total = recent.count()
        errors = recent.filter(status_code__gte=400).count()

        top_endpoints = list(
            recent.values("path").annotate(count=Count("id")).order_by("-count")[:10]
        )
        status_breakdown = dict(
            recent.values_list("status_code").annotate(c=Count("id")).order_by()
        )

        return Response({
            "window": "last_24h",
            "total_requests": total,
            "error_count": errors,
            "error_rate_percent": round(errors / total * 100, 2) if total else 0,
            "top_endpoints": top_endpoints,
            "status_code_breakdown": status_breakdown,
            "requests_today": AuditLog.objects.filter(created_at__date=today).count(),
        })
