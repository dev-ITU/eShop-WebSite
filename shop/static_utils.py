from django.conf import settings
from django.templatetags.static import static


def product_static_url(path):
    if not path:
        return ""
    try:
        return static(path)
    except ValueError:
        static_url = settings.STATIC_URL
        if not static_url.endswith("/"):
            static_url = f"{static_url}/"
        if not static_url.startswith(("http://", "https://", "/")):
            static_url = f"/{static_url}"
        return f"{static_url}{str(path).lstrip('/')}"
