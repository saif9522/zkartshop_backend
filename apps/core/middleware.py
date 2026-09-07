class AuditLogMiddleware:
    """
    Lightweight audit trail: logs every /api/ request with the acting user,
    method, path, status code and IP. Kept out of the request/response cycle
    critical path — write happens after the response is ready.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.path.startswith("/api/") and request.method not in ("GET", "OPTIONS"):
            self._log(request, response)

        return response

    @staticmethod
    def _log(request, response):
        from apps.core.models import AuditLog

        user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR"))
        AuditLog.objects.create(
            user=user,
            method=request.method,
            path=request.path[:255],
            status_code=response.status_code,
            ip_address=ip.split(",")[0].strip() if ip else None,
        )
