from django.db import DatabaseError

from .models import PageView


SKIPPED_PREFIXES = (
    "/static/",
    "/favicon",
    "/media/",
    "/api/",
    "/admin/jsi18n/",
)


class PageViewMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        should_track = self.should_track(request)
        if should_track and hasattr(request, "session") and not request.session.session_key:
            request.session.create()
            request.session.modified = True

        response = self.get_response(request)

        if should_track:
            self.record_view(request, response)
        return response

    def should_track(self, request):
        if request.method != "GET":
            return False
        path = request.path or "/"
        return not any(path.startswith(prefix) for prefix in SKIPPED_PREFIXES)

    def record_view(self, request, response):
        try:
            user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
            PageView.objects.create(
                path=(request.path or "/")[:260],
                full_path=request.get_full_path(),
                method=request.method,
                status_code=getattr(response, "status_code", 200) or 200,
                user=user,
                session_key=getattr(request.session, "session_key", "") or "",
                ip_address=self.client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:2000],
                referrer=request.META.get("HTTP_REFERER", "")[:2000],
                device=self.device_from_user_agent(request.META.get("HTTP_USER_AGENT", "")),
                is_staff_area=(request.path or "").startswith("/control/"),
            )
        except (DatabaseError, RuntimeError):
            return

    def client_ip(self, request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip() or None
        return request.META.get("REMOTE_ADDR") or None

    def device_from_user_agent(self, user_agent):
        ua = user_agent.lower()
        if "ipad" in ua or "tablet" in ua:
            return "tablet"
        if "mobile" in ua or "iphone" in ua or "android" in ua:
            return "mobile"
        return "desktop"
