import os
import logging
from django.conf import settings
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are the friendly customer support assistant for zKart.shop, a quick-commerce "
    "marketplace delivering groceries, fruits, medicines, electronics and more. Be warm, "
    "concise, and helpful (keep answers within 1-3 sentences). Answer user questions "
    "about products, store info, orders, or general queries naturally and politely. "
    "Reply in the same language or style the customer writes in (Hindi, Hinglish, or English)."
)

class ChatbotUnavailable(Exception):
    pass

def get_chat_reply(user, message_history):
    """
    Chat handler using gemini-3.6-flash safely without unsupported parameters.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise ChatbotUnavailable("AI chatbot is not configured (GEMINI_API_KEY not set).")

    try:
        client = genai.Client(api_key=api_key)

        recent_history = message_history[-10:] if message_history else []
        
        contents = []
        for m in recent_history:
            raw_role = str(m.get("role", "user")).lower()
            role = "model" if raw_role in ["assistant", "model", "bot"] else "user"
            
            content_text = str(m.get("content", "")).strip()
            if content_text:
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=content_text)]
                    )
                )

        if not contents:
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Hello")]
                )
            )

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=400,
            ),
        )
        
        return response.text if response and response.text else "Jee, main aapki kya madad kar sakta hoon?"

    except Exception as exc:
        logger.exception("Gemini chatbot request failed safely")
        raise ChatbotUnavailable(f"Gemini error: {str(exc)}")
