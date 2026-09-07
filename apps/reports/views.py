from datetime import date, timedelta

from django.utils import timezone

from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reports.models import AIReport
from apps.reports.services import (
    build_accounting_report_rows,
    build_gst_report_rows,
    build_inventory_report_rows,
    build_order_report_rows,
    build_sales_report_rows,
    build_vendor_report_rows,
    summarise_accounting_rows,
    rows_to_csv_response,
    rows_to_excel_response,
)
from apps.superadmin.permissions import CanViewReports


def _parse_date_range(request, default_days=30):
    today = timezone.localdate()
    date_from = request.query_params.get("from")
    date_to = request.query_params.get("to")
    try:
        date_from = date.fromisoformat(date_from) if date_from else today - timedelta(days=default_days)
        date_to = date.fromisoformat(date_to) if date_to else today
    except ValueError as exc:
        raise ValidationError({"detail": "Invalid date — use YYYY-MM-DD for ?from= and ?to=."}) from exc
    return date_from, date_to


def _respond(request, rows, filename, sheet_title):
    fmt = request.query_params.get("export", "csv").lower()
    if fmt == "xlsx":
        return rows_to_excel_response(rows, filename, sheet_title)
    return rows_to_csv_response(rows, filename)


class SalesReportView(APIView):
    permission_classes = [permissions.IsAuthenticated, CanViewReports]

    def get(self, request):
        date_from, date_to = _parse_date_range(request)
        rows = build_sales_report_rows(date_from, date_to)
        return _respond(request, rows, f"sales_report_{date_from}_{date_to}", "Sales")


class OrderReportView(APIView):
    permission_classes = [permissions.IsAuthenticated, CanViewReports]

    def get(self, request):
        date_from, date_to = _parse_date_range(request)
        rows = build_order_report_rows(date_from, date_to, status=request.query_params.get("status"))
        return _respond(request, rows, f"order_report_{date_from}_{date_to}", "Orders")


class VendorReportView(APIView):
    permission_classes = [permissions.IsAuthenticated, CanViewReports]

    def get(self, request):
        rows = build_vendor_report_rows()
        return _respond(request, rows, "vendor_report", "Vendors")


class InventoryReportView(APIView):
    """Admin sees every vendor's inventory; a vendor hitting this only ever sees their own."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if request.user.role == "vendor":
            if not hasattr(request.user, "vendor_profile"):
                return Response({"detail": "You haven't registered a shop yet."}, status=404)
            vendor_id = request.user.vendor_profile.id
        elif CanViewReports().has_permission(request, self):
            vendor_id = request.query_params.get("vendor")
        else:
            return Response({"detail": "Admin or vendor access required."}, status=403)

        rows = build_inventory_report_rows(vendor_id)
        return _respond(request, rows, "inventory_report", "Inventory")


class GSTReportView(APIView):
    permission_classes = [permissions.IsAuthenticated, CanViewReports]

    def get(self, request):
        date_from, date_to = _parse_date_range(request)
        rows = build_gst_report_rows(date_from, date_to)
        return _respond(request, rows, f"gst_report_{date_from}_{date_to}", "GST")


class AccountingReportView(APIView):
    """
    Money/accounting report for the admin & super-admin panels.

    Query params:
      period=day|week|month|year        (time bucket, default month)
      group_by=user|vendor|shop         (optional extra breakdown)
      status=<order status>             (optional filter, e.g. delivered)
      payment_method=cod|razorpay|wallet(optional filter)
      from=YYYY-MM-DD & to=YYYY-MM-DD   (date range, default last 365 days)
      export=json|csv|xlsx              (default json for the panel; csv/xlsx download)
    """

    permission_classes = [permissions.IsAuthenticated, CanViewReports]

    VALID_PERIODS = {"day", "week", "month", "year"}
    VALID_GROUPS = {"user", "vendor", "shop"}

    def get(self, request):
        # Accounting screens usually default to a full year, not 30 days.
        date_from, date_to = _parse_date_range(request, default_days=365)

        period = (request.query_params.get("period") or "month").lower()
        if period not in self.VALID_PERIODS:
            raise ValidationError({"detail": "period must be one of: day, week, month, year."})

        group_by = request.query_params.get("group_by")
        if group_by and group_by.lower() not in self.VALID_GROUPS:
            raise ValidationError({"detail": "group_by must be one of: user, vendor, shop."})

        rows = build_accounting_report_rows(
            date_from,
            date_to,
            period=period,
            group_by=group_by,
            status=request.query_params.get("status"),
            payment_method=request.query_params.get("payment_method"),
        )

        fmt = request.query_params.get("export", "json").lower()
        filename = f"accounting_{period}_{date_from}_{date_to}"
        if fmt == "xlsx":
            return rows_to_excel_response(rows, filename, "Accounting")
        if fmt == "csv":
            return rows_to_csv_response(rows, filename)

        return Response({
            "period": period,
            "group_by": group_by or None,
            "from": date_from.isoformat(),
            "to": date_to.isoformat(),
            "summary": summarise_accounting_rows(rows),
            "rows": rows,
        })


class AISummaryView(APIView):
    """Latest (or a specific date's) AI-generated plain-language sales summary."""

    permission_classes = [permissions.IsAuthenticated, CanViewReports]

    def get(self, request):
        report_date = request.query_params.get("date")
        if report_date:
            try:
                date.fromisoformat(report_date)
            except ValueError as exc:
                raise ValidationError({"detail": "Invalid date — use YYYY-MM-DD for ?date=."}) from exc
        qs = AIReport.objects.filter(report_date=report_date) if report_date else AIReport.objects.all()
        report = qs.first()
        if not report:
            return Response({"detail": "No AI report available for this date yet."}, status=404)
        return Response({
            "report_date": report.report_date,
            "summary": report.summary_text,
            "raw_data": report.raw_data,
            "model_used": report.model_used,
            "created_at": report.created_at,
        })


class TriggerAISummaryView(APIView):
    """Manually (re)generate today's AI sales summary instead of waiting for the nightly Celery job."""

    permission_classes = [permissions.IsAuthenticated, CanViewReports]

    def post(self, request):
        from apps.core.task_utils import safe_delay
        from apps.reports.tasks import generate_daily_ai_sales_report

        if not safe_delay(generate_daily_ai_sales_report):
            return Response(
                {"detail": "Background job queue (Redis/Celery) is unreachable right now. Is Redis running?"},
                status=503,
            )
        return Response({"detail": "AI summary generation started."}, status=202)
