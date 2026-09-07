import json
import logging

from celery import shared_task
from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


def _build_daily_aggregates(report_date):
    from apps.orders.models import Order, OrderItem

    orders = Order.objects.filter(placed_at__date=report_date)
    delivered = orders.filter(status=Order.Status.DELIVERED)
    cancelled = orders.filter(status=Order.Status.CANCELLED)

    revenue = delivered.aggregate(t=Sum("grand_total"))["t"] or 0

    top_vendors = list(
        delivered.values("vendor__shop_name")
        .annotate(revenue=Sum("grand_total"), order_count=Count("id"))
        .order_by("-revenue")[:5]
    )
    top_products = list(
        OrderItem.objects.filter(order__in=delivered)
        .values("product_name")
        .annotate(units_sold=Sum("quantity"), revenue=Sum("price"))
        .order_by("-units_sold")[:5]
    )

    return {
        "date": report_date.isoformat(),
        "total_orders": orders.count(),
        "delivered_orders": delivered.count(),
        "cancelled_orders": cancelled.count(),
        "revenue": float(revenue),
        "top_vendors": [
            {"shop_name": v["vendor__shop_name"], "revenue": float(v["revenue"] or 0), "orders": v["order_count"]}
            for v in top_vendors
        ],
        "top_products": [
            {"product_name": p["product_name"], "units_sold": p["units_sold"], "revenue": float(p["revenue"] or 0)}
            for p in top_products
        ],
    }


def _call_anthropic(aggregates):
    """
    Sends the day's aggregates to Claude and asks for a short, plain-language
    summary for the admin dashboard — the kind of one-paragraph "what
    happened today" a busy operator can read in five seconds.
    """
    import requests

    prompt = (
        "You are summarizing one day's sales data for the admin dashboard of "
        "'zKart.shop', a quick-commerce marketplace. Write a short "
        "(3-5 sentence) plain-language summary of the day — call out the "
        "revenue, order volume, any standout vendor or product, and the "
        "cancellation rate if notable. No headers, no bullet points, just "
        "prose a busy operator can read in five seconds.\n\n"
        f"Today's data:\n{json.dumps(aggregates, indent=2)}"
    )

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": settings.ANTHROPIC_MODEL,
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    text = "".join(block["text"] for block in data["content"] if block["type"] == "text")
    return text, data.get("model", settings.ANTHROPIC_MODEL)


@shared_task
def generate_daily_ai_sales_report(report_date=None):
    """
    Runs daily at 23:45 IST (see mall_of_garhwa/celery.py beat_schedule).
    Aggregates the day's orders and asks Claude to write a plain-language
    summary for the admin dashboard, storing both in AIReport.
    """
    from apps.reports.models import AIReport

    report_date = report_date or timezone.localdate()
    aggregates = _build_daily_aggregates(report_date)

    if not settings.ANTHROPIC_API_KEY:
        summary = (
            f"[DEV] {aggregates['total_orders']} orders today, "
            f"{aggregates['delivered_orders']} delivered, revenue ₹{aggregates['revenue']:.2f}. "
            "(ANTHROPIC_API_KEY not set — this is a placeholder, not an AI-generated summary.)"
        )
        model_used = ""
    else:
        try:
            summary, model_used = _call_anthropic(aggregates)
        except Exception as exc:
            logger.error("AI sales report generation failed: %s", exc)
            summary = f"AI summary generation failed: {exc}"
            model_used = ""

    report, _ = AIReport.objects.update_or_create(
        report_date=report_date,
        defaults={"summary_text": summary, "raw_data": aggregates, "model_used": model_used},
    )
    logger.info("generate_daily_ai_sales_report: report for %s saved (id=%s)", report_date, report.id)
    return {"report_id": str(report.id), "summary": summary}
