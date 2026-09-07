from django.urls import path

from apps.reports.views import (
    AccountingReportView,
    AISummaryView,
    GSTReportView,
    InventoryReportView,
    OrderReportView,
    SalesReportView,
    TriggerAISummaryView,
    VendorReportView,
)

urlpatterns = [
    path("accounting/", AccountingReportView.as_view(), name="accounting-report"),
    path("sales/", SalesReportView.as_view(), name="sales-report"),
    path("orders/", OrderReportView.as_view(), name="order-report"),
    path("vendors/", VendorReportView.as_view(), name="vendor-report"),
    path("inventory/", InventoryReportView.as_view(), name="inventory-report"),
    path("gst/", GSTReportView.as_view(), name="gst-report"),
    path("ai-summary/", AISummaryView.as_view(), name="ai-summary"),
    path("ai-summary/trigger/", TriggerAISummaryView.as_view(), name="ai-summary-trigger"),
]
