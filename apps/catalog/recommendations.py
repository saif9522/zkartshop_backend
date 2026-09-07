"""
Product recommendations — deliberately rule-based/data-driven rather than an
LLM call per page view: recommendations need to render in milliseconds on
every product/home page load, and an LLM round-trip per request would be
both too slow and needlessly expensive for what is fundamentally a
"similar items" / "co-purchase" lookup. The AI chatbot (apps.chatbot) is
where an actual LLM call makes sense — a user-initiated, one-off request.
"""
from django.db.models import Count, Q

from apps.catalog.models import Product


def similar_products(product, limit=10):
    """Same category, available, excluding itself — ranked by rating then popularity."""
    return (
        Product.objects.filter(
            category=product.category, is_available=True, vendor__status="approved", vendor__is_open=True,
        )
        .exclude(id=product.id)
        .select_related("vendor", "category")
        .prefetch_related("images")
        .order_by("-rating_avg", "-rating_count")[:limit]
    )


def frequently_bought_together(product, limit=6):
    """
    Products that showed up in the same orders as this one, ranked by how
    often that co-occurrence happened. Pure correlation from real order
    history — the classic "customers who bought this also bought" widget.
    """
    from apps.orders.models import OrderItem

    order_ids = OrderItem.objects.filter(product=product).values_list("order_id", flat=True)[:500]
    co_purchased = (
        OrderItem.objects.filter(order_id__in=list(order_ids))
        .exclude(product=product)
        .values("product_id")
        .annotate(times_bought_together=Count("id"))
        .order_by("-times_bought_together")[:limit]
    )
    product_ids = [row["product_id"] for row in co_purchased]
    if not product_ids:
        return Product.objects.none()

    # Preserve the co-occurrence ranking order (a plain filter() would lose it).
    products = Product.objects.filter(
        id__in=product_ids, is_available=True, vendor__status="approved", vendor__is_open=True,
    ).select_related("vendor", "category").prefetch_related("images")
    by_id = {p.id: p for p in products}
    return [by_id[pid] for pid in product_ids if pid in by_id]


def recommended_for_you(user, limit=12):
    """
    Personalized home-page picks: top categories from the customer's own
    order history, best-rated available products in those categories they
    haven't already bought. Falls back to platform-wide trending products
    for a new customer with no order history yet (or an anonymous visitor).
    """
    from apps.orders.models import Order, OrderItem

    if user and user.is_authenticated:
        purchased_product_ids = set(
            OrderItem.objects.filter(order__customer=user).values_list("product_id", flat=True)
        )
        top_category_ids = list(
            OrderItem.objects.filter(order__customer=user)
            .values_list("product__category_id", flat=True)
            .annotate(n=Count("id"))
            .order_by("-n")[:5]
        )
        if top_category_ids:
            picks = (
                Product.objects.filter(
                    category_id__in=top_category_ids, is_available=True,
                    vendor__status="approved", vendor__is_open=True,
                )
                .exclude(id__in=purchased_product_ids)
                .select_related("vendor", "category")
                .prefetch_related("images")
                .order_by("-rating_avg", "-rating_count")[:limit]
            )
            if picks:
                return picks

    # Trending fallback — most-ordered products in the last 30 days.
    from datetime import timedelta

    from django.utils import timezone

    since = timezone.now() - timedelta(days=30)
    trending_ids = list(
        OrderItem.objects.filter(order__placed_at__gte=since)
        .exclude(order__status=Order.Status.CANCELLED)
        .values_list("product_id", flat=True)
        .annotate(n=Count("id"))
        .order_by("-n")[:limit]
    )
    if trending_ids:
        products = Product.objects.filter(
            id__in=trending_ids, is_available=True, vendor__status="approved", vendor__is_open=True,
        ).select_related("vendor", "category").prefetch_related("images")
        by_id = {p.id: p for p in products}
        ordered = [by_id[pid] for pid in trending_ids if pid in by_id]
        if ordered:
            return ordered

    # Nothing trending either (fresh platform) — just show featured/highly-rated products.
    return (
        Product.objects.filter(is_available=True, vendor__status="approved", vendor__is_open=True)
        .select_related("vendor", "category")
        .prefetch_related("images")
        .order_by("-is_featured", "-rating_avg")[:limit]
    )
