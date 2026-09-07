"""
The rest of this API authenticates with JWT bearer tokens, not session
cookies, so Channels' default AuthMiddlewareStack (session-based) doesn't
apply here. WebSocket clients can't set arbitrary headers easily from a
browser, so the access token is passed as a query param instead:

    wss://.../ws/orders/<order_id>/track/?token=<access_token>
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        token = parse_qs(query_string).get("token", [None])[0]
        scope["user"] = await self._get_user(token)
        return await super().__call__(scope, receive, send)

    @database_sync_to_async
    def _get_user(self, token):
        if not token:
            return AnonymousUser()
        try:
            from rest_framework_simplejwt.tokens import AccessToken

            from apps.accounts.models import User

            validated = AccessToken(token)
            return User.objects.get(id=validated["user_id"])
        except Exception:
            return AnonymousUser()
