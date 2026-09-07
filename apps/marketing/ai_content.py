import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class AIContentUnavailable(Exception):
    pass


def generate_campaign_content(topic, product_name="", tone="friendly and exciting"):
    """
    Drafts email subject/body, a WhatsApp message, and a social caption +
    hashtags for a campaign topic (e.g. a new product launch, a festival
    sale). The admin always reviews/edits this in the Preview screen before
    anything is actually sent — this never publishes on its own.
    """
    if not settings.ANTHROPIC_API_KEY:
        raise AIContentUnavailable("AI content generation is not configured (ANTHROPIC_API_KEY not set).")

    product_line = f' for the product "{product_name}"' if product_name else ""
    prompt = (
        f"Write marketing campaign copy{product_line} for zKart.shop, a quick-commerce grocery/essentials "
        f"marketplace. Topic: {topic}. Tone: {tone}.\n\n"
        "Return ONLY valid JSON (no markdown fences, no commentary) with exactly these keys:\n"
        '{"email_subject": "...", "email_body": "...", "whatsapp_message": "...", '
        '"social_caption": "...", "hashtags": ["...", "..."]}\n\n'
        "email_body: 2-4 short paragraphs, plain text. whatsapp_message: under 300 characters, "
        "casual, can use 1-2 emoji. social_caption: under 200 characters, punchy, for Facebook/Instagram. "
        "hashtags: 5-8 relevant tags without the # symbol."
    )

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.ANTHROPIC_MODEL,
                "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        text = "".join(block["text"] for block in data["content"] if block["type"] == "text")
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)
    except Exception as exc:
        logger.error("AI campaign content generation failed: %s", exc)
        raise AIContentUnavailable(f"Could not generate content: {exc}") from exc
