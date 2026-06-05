from decimal import Decimal

from .models import Product
from .static_utils import product_static_url

CART_SESSION_KEY = "cart"


def money(value):
    amount = Decimal(value).quantize(Decimal("1"))
    return f"{amount:,.0f}".replace(",", " ")


def get_cart(session):
    cart = session.get(CART_SESSION_KEY, {})
    return {str(product_id): int(quantity) for product_id, quantity in cart.items() if int(quantity) > 0}


def save_cart(session, cart):
    session[CART_SESSION_KEY] = {str(product_id): int(quantity) for product_id, quantity in cart.items() if int(quantity) > 0}
    session.modified = True


def cart_count(session):
    return sum(get_cart(session).values())


def cart_snapshot(session):
    cart = get_cart(session)
    product_ids = [int(product_id) for product_id in cart]
    products = Product.objects.filter(id__in=product_ids, is_active=True).select_related("category")
    products_by_id = {product.id: product for product in products}
    items = []
    total = Decimal("0")

    for product_id_raw, quantity in cart.items():
        product = products_by_id.get(int(product_id_raw))
        if not product:
            continue
        line_total = product.price * quantity
        total += line_total
        items.append(
            {
                "id": product.id,
                "name": product.name,
                "slug": product.slug,
                "url": product.get_absolute_url(),
                "brand": product.brand,
                "category": product.category.name,
                "image": product_static_url(product.image),
                "price": float(product.price),
                "price_display": money(product.price),
                "quantity": quantity,
                "stock": product.stock,
                "line_total": float(line_total),
                "line_total_display": money(line_total),
            }
        )

    return {
        "items": items,
        "count": sum(item["quantity"] for item in items),
        "total": float(total),
        "total_display": money(total),
    }
