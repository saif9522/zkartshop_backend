import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the customer support assistant for zKart.shop, a quick-commerce "
    "marketplace delivering groceries, fruits, medicines and more. Be warm, "
    "concise, and helpful — most answers should be 1-3 sentences. Use the "
    "tools available to look up real products, the customer's own orders, "
    "and FAQs rather than guessing. Never invent prices, stock status, or "
    "order details — if a tool doesn't return what's needed, say so plainly "
    "and suggest contacting support. Reply in the same language/style the "
    "customer writes in (Hindi, Hinglish, or English)."
)

TOOLS = [
    {
        "name": "search_products",
        "description": "Search the product catalog by name or keyword. Returns matching products with price, unit, and stock status.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search keywords, e.g. 'rice' or 'milk 500ml'"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_my_orders",
        "description": "Get the customer's most recent orders with their current status.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_order_detail",
        "description": "Get full detail (items, status, delivery address, payment) for one of the customer's own orders by order number.",
        "input_schema": {
            "type": "object",
            "properties": {"order_number": {"type": "string"}},
            "required": ["order_number"],
        },
    },
    {
        "name": "search_faqs",
        "description": "Search the store's FAQ list for policy/how-to questions (returns, delivery time, payment methods, etc).",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string", "description": "What the customer is asking about"}},
            "required": ["topic"],
        },
    },
]


def _execute_tool(name, tool_input, user):
    from django.db.models import Q

    if name == "search_products":
        from apps.catalog.models import Product

        query = tool_input.get("query", "")
        products = Product.objects.filter(
            name__icontains=query, is_available=True, vendor__status="approved", vendor__is_open=True,
        ).select_related("vendor")[:5]
        if not products:
            return {"results": [], "note": "No matching products found."}
        return {
            "results": [
                {
                    "name": p.name, "unit": p.unit, "price": str(p.selling_price),
                    "in_stock": p.stock_quantity > 0, "shop": p.vendor.shop_name,
                }
                for p in products
            ]
        }

    if name == "get_my_orders":
        from apps.orders.models import Order

        orders = Order.objects.filter(customer=user).order_by("-placed_at")[:5]
        return {
            "orders": [
                {"order_number": o.order_number, "status": o.status, "total": str(o.grand_total), "placed_at": str(o.placed_at)}
                for o in orders
            ]
        }

    if name == "get_order_detail":
        from apps.orders.models import Order

        order_number = tool_input.get("order_number", "")
        order = Order.objects.filter(customer=user, order_number__iexact=order_number).select_related("vendor").first()
        if not order:
            return {"error": "No order found with that number for this customer."}
        return {
            "order_number": order.order_number,
            "status": order.status,
            "vendor": order.vendor.shop_name,
            "total": str(order.grand_total),
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "items": [
                {"product": i.product_name, "quantity": i.quantity, "subtotal": str(i.subtotal)}
                for i in order.items.all()
            ],
        }

    if name == "search_faqs":
        from apps.cms.models import FAQ

        topic = tool_input.get("topic", "")
        qs = FAQ.objects.filter(is_active=True)
        if topic:
            qs = qs.filter(Q(question__icontains=topic) | Q(answer__icontains=topic))
        faqs = qs[:3]
        return {"faqs": [{"question": f.question, "answer": f.answer} for f in faqs]}

    return {"error": f"Unknown tool: {name}"}


class ChatbotUnavailable(Exception):
    pass


def get_chat_reply(user, message_history):
    """
    message_history: list of {"role": "user"|"assistant", "content": str}
    (the new user message should already be the last entry).
    Returns the assistant's final text reply after resolving any tool calls.
    """
    if not settings.ANTHROPIC_API_KEY:
        raise ChatbotUnavailable("AI chatbot is not configured (ANTHROPIC_API_KEY not set).")

    messages = [{"role": m["role"], "content": m["content"]} for m in message_history]
    headers = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    # Bounded loop — a well-behaved conversation resolves in 1-3 tool round-trips;
    # this just guards against an unexpected infinite tool-call loop.
    for _ in range(5):
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json={
                "model": settings.ANTHROPIC_MODEL,
                "max_tokens": 500,
                "system": SYSTEM_PROMPT,
                "tools": TOOLS,
                "messages": messages,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("stop_reason") != "tool_use":
            return "".join(block["text"] for block in data["content"] if block["type"] == "text").strip()

        messages.append({"role": "assistant", "content": data["content"]})
        tool_results = []
        for block in data["content"]:
            if block["type"] != "tool_use":
                continue
            try:
                result = _execute_tool(block["name"], block.get("input", {}), user)
            except Exception as exc:
                logger.exception("Chatbot tool %s failed", block["name"])
                result = {"error": str(exc)}
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block["id"], "content": json.dumps(result)}
            )
        messages.append({"role": "user", "content": tool_results})

    return "Sorry, I'm having trouble with that request right now — please try rephrasing, or contact support."
