import csv
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import (
    Coalesce,
    TruncDate,
    TruncMonth,
    TruncWeek,
    TruncYear,
)
from django.http import HttpResponse

from apps.catalog.models import Product
from apps.orders.models import Order

GST_RATE_PERCENT = Decimal("5")  # flat estimate — real per-category GST slabs are a Phase-11-scale project


def build_sales_report_rows(date_from, date_to):
    qs = (
        Order.objects.filter(placed_at__date__gte=date_from, placed_at__date__lte=date_to)
        .annotate(day=TruncDate("placed_at"))
        .values("day")
        .annotate(order_count=Count("id"), revenue=Sum("grand_total"))
        .order_by("day")
    )
    return [
        {"date": row["day"].isoformat(), "order_count": row["order_count"], "revenue": row["revenue"] or 0}
        for row in qs
    ]


def build_order_report_rows(date_from, date_to, status=None):
    qs = Order.objects.filter(placed_at__date__gte=date_from, placed_at__date__lte=date_to).select_related(
        "vendor", "customer"
    )
    if status:
        qs = qs.filter(status=status)
    return [
        {
            "order_number": o.order_number,
            "date": o.placed_at.date().isoformat(),
            "vendor": o.vendor.shop_name,
            "customer_phone": str(o.customer.phone) if o.customer.phone else "",
            "status": o.status,
            "payment_method": o.payment_method,
            "payment_status": o.payment_status,
            "subtotal": o.subtotal,
            "delivery_charge": o.delivery_charge,
            "discount": o.discount_amount,
            "grand_total": o.grand_total,
        }
        for o in qs
    ]


def build_vendor_report_rows():
    from apps.vendors.models import Vendor

    rows = []
    for vendor in Vendor.objects.all():
        delivered = Order.objects.filter(vendor=vendor, status=Order.Status.DELIVERED)
        agg = delivered.aggregate(order_count=Count("id"), revenue=Sum("subtotal"))
        revenue = agg["revenue"] or 0
        commission_earned = round(revenue * vendor.commission_percent / 100, 2)
        rows.append({
            "shop_name": vendor.shop_name,
            "category": vendor.category,
            "status": vendor.status,
            "delivered_orders": agg["order_count"] or 0,
            "gross_revenue": revenue,
            "commission_percent": vendor.commission_percent,
            "commission_earned_by_platform": commission_earned,
            "net_payable_to_vendor": revenue - commission_earned,
        })
    return rows


def build_inventory_report_rows(vendor_id=None):
    qs = Product.objects.select_related("vendor", "category")
    if vendor_id:
        qs = qs.filter(vendor_id=vendor_id)
    return [
        {
            "product": p.name,
            "vendor": p.vendor.shop_name,
            "category": p.category.name,
            "unit": p.unit,
            "mrp": p.mrp,
            "selling_price": p.selling_price,
            "stock_quantity": p.stock_quantity,
            "is_available": p.is_available,
        }
        for p in qs
    ]


def build_gst_report_rows(date_from, date_to):
    """Estimated GST breakdown — subtotal is treated as GST-inclusive at GST_RATE_PERCENT for this estimate."""
    qs = Order.objects.filter(
        placed_at__date__gte=date_from, placed_at__date__lte=date_to, status=Order.Status.DELIVERED
    ).select_related("vendor")
    rows = []
    for o in qs:
        taxable_value = round(o.subtotal / (1 + GST_RATE_PERCENT / 100), 2)
        gst_amount = round(o.subtotal - taxable_value, 2)
        rows.append({
            "order_number": o.order_number,
            "date": o.placed_at.date().isoformat(),
            "vendor": o.vendor.shop_name,
            "vendor_gst_number": o.vendor.gst_number,
            "taxable_value": taxable_value,
            "gst_rate_percent": GST_RATE_PERCENT,
            "gst_amount": gst_amount,
            "order_subtotal": o.subtotal,
        })
    return rows


# ---------------------------------------------------------------------------
# Accounting / payments report
# ---------------------------------------------------------------------------
# One report that answers "how much money moved" sliced two independent ways:
#   * period   — day / week / month / year  (time bucket)
#   * group_by — none / user / vendor(=shop) (who the money is attributed to)
# Vendor and shop are the same entity in the current data model (one shop =
# one Vendor row), so group_by="shop" and group_by="vendor" behave identically.

_PERIOD_TRUNC = {
    "day": TruncDate,
    "week": TruncWeek,
    "month": TruncMonth,
    "year": TruncYear,
}

# group_by aliases -> the Order field(s) we bucket on. "shop" is an alias of
# "vendor" because a shop *is* a vendor here.
_GROUP_FIELDS = {
    "user": "customer",
    "vendor": "vendor",
    "shop": "vendor",
}


def _money(field, condition=None):
    """Sum() of a money field, coalesced to 0, optionally filtered by a Q()."""
    kwargs = {"output_field": DecimalField(max_digits=14, decimal_places=2)}
    if condition is not None:
        kwargs["filter"] = condition
    return Coalesce(
        Sum(field, **kwargs),
        Value(Decimal("0.00")),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def build_accounting_report_rows(
    date_from,
    date_to,
    period="month",
    group_by=None,
    status=None,
    payment_method=None,
):
    """
    Aggregated money report for the admin / super-admin accounting screen.

    period:        day | week | month | year   (defaults to month)
    group_by:      None | user | vendor | shop  (extra breakdown per bucket)
    status:        optional Order.Status filter (e.g. only 'delivered')
    payment_method optional Order.PaymentMethod filter (cod / razorpay / wallet)
    """
    period = (period or "month").lower()
    if period not in _PERIOD_TRUNC:
        period = "month"
    trunc = _PERIOD_TRUNC[period]

    qs = Order.objects.filter(placed_at__date__gte=date_from, placed_at__date__lte=date_to)
    if status:
        qs = qs.filter(status=status)
    if payment_method:
        qs = qs.filter(payment_method=payment_method)

    qs = qs.annotate(bucket=trunc("placed_at"))

    values = ["bucket"]
    group_key = _GROUP_FIELDS.get((group_by or "").lower())
    if group_key == "customer":
        values += ["customer_id", "customer__phone", "customer__full_name"]
    elif group_key == "vendor":
        values += ["vendor_id", "vendor__shop_name"]

    paid_q = Q(payment_status=Order.PaymentStatus.PAID)
    pending_q = Q(payment_status=Order.PaymentStatus.PENDING)
    cod_q = Q(payment_method=Order.PaymentMethod.COD)
    online_q = ~Q(payment_method=Order.PaymentMethod.COD)
    cancelled_q = Q(status=Order.Status.CANCELLED)

    aggregated = (
        qs.values(*values)
        .annotate(
            order_count=Count("id"),
            cancelled_orders=Count("id", filter=cancelled_q),
            items_subtotal=_money("subtotal"),
            delivery_charges=_money("delivery_charge"),
            discounts=_money("discount_amount"),
            gross_sales=_money("grand_total"),
            paid_amount=_money("grand_total", paid_q),
            pending_amount=_money("grand_total", pending_q),
            cod_amount=_money("grand_total", cod_q),
            online_amount=_money("grand_total", online_q),
        )
        .order_by("bucket", *[v for v in values if v != "bucket"])
    )

    def _fmt_bucket(value):
        if value is None:
            return ""
        if period == "year":
            return value.strftime("%Y")
        if period == "month":
            return value.strftime("%Y-%m")
        # day and week both anchor on a date; TruncWeek yields a datetime,
        # TruncDate yields a date — normalise both to a plain YYYY-MM-DD.
        if hasattr(value, "date"):
            value = value.date()
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    rows = []
    for r in aggregated:
        row = {"period": period, "bucket": _fmt_bucket(r["bucket"])}
        if group_key == "customer":
            row["customer"] = r.get("customer__full_name") or str(r.get("customer__phone") or "") or "—"
        elif group_key == "vendor":
            row["shop"] = r.get("vendor__shop_name") or "—"
        row.update({
            "order_count": r["order_count"],
            "cancelled_orders": r["cancelled_orders"],
            "items_subtotal": r["items_subtotal"],
            "delivery_charges": r["delivery_charges"],
            "discounts": r["discounts"],
            "gross_sales": r["gross_sales"],
            "paid_amount": r["paid_amount"],
            "pending_amount": r["pending_amount"],
            "cod_amount": r["cod_amount"],
            "online_amount": r["online_amount"],
        })
        rows.append(row)
    return rows


def summarise_accounting_rows(rows):
    """Totals across every row — used for the JSON summary card on the panel."""
    money_fields = [
        "items_subtotal", "delivery_charges", "discounts", "gross_sales",
        "paid_amount", "pending_amount", "cod_amount", "online_amount",
    ]
    totals = {f: Decimal("0.00") for f in money_fields}
    order_count = 0
    cancelled = 0
    for r in rows:
        order_count += r.get("order_count", 0)
        cancelled += r.get("cancelled_orders", 0)
        for f in money_fields:
            totals[f] += Decimal(str(r.get(f, 0) or 0))
    return {"order_count": order_count, "cancelled_orders": cancelled, **{f: totals[f] for f in money_fields}}


def rows_to_csv_response(rows, filename):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
    if not rows:
        response.write("No data for the selected range.\n")
        return response
    writer = csv.DictWriter(response, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return response


def rows_to_excel_response(rows, filename, sheet_title="Report"):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]

    if rows:
        headers = list(rows[0].keys())
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in rows:
            ws.append([row[h] for h in headers])
        for col in ws.columns:
            width = max(len(str(c.value)) for c in col if c.value is not None) + 2
            ws.column_dimensions[col[0].column_letter].width = min(width, 40)
    else:
        ws.append(["No data for the selected range."])

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
    wb.save(response)
    return response
