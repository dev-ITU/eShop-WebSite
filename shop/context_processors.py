from django.db import DatabaseError, ProgrammingError

from .models import Category, SiteContent
from .views_cart import cart_count


def catalog_nav(request):
    try:
        site_content = {
            item.key: item
            for item in SiteContent.objects.filter(is_active=True).only("key", "title", "body", "block_type")
        }
    except (DatabaseError, ProgrammingError):
        site_content = {}
    return {
        "nav_categories": Category.objects.filter(is_active=True).order_by("sort_order", "name")[:8],
        "cart_count": cart_count(request.session),
        "site_content": site_content,
    }
