import json
import secrets
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Max, Min, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from .forms import CheckoutForm, PasswordResetConfirmForm, PasswordResetRequestForm, RegisterForm
from .models import Category, CustomerProfile, Order, OrderItem, Product
from .static_utils import product_static_url
from .tasks import complete_demo_payment, process_order_payment
from .views_cart import cart_snapshot, get_cart, money, save_cart


HIDDEN_ATTRIBUTE_KEYS = {"url", "источник", "раздел", "source", "source url"}
GUEST_ORDER_SESSION_KEY = "guest_order_ids"
PENDING_REGISTRATION_SESSION_KEY = "pending_registration"
PENDING_PASSWORD_RESET_SESSION_KEY = "pending_password_reset"
User = get_user_model()


def public_product_attributes(attributes, product=None):
    visible = {}
    for key, value in (attributes or {}).items():
        key_text = str(key).strip()
        value_text = str(value).strip()
        if not key_text or not value_text:
            continue
        if key_text.lower() in HIDDEN_ATTRIBUTE_KEYS or "url" in key_text.lower():
            continue
        if "http://" in value_text.lower() or "https://" in value_text.lower():
            continue
        visible[key_text] = value

    if product:
        if product.color:
            visible.pop("Цвет", None)
        if product.memory:
            for key in list(visible):
                if key.lower() in {"объем встроенной памяти", "встроенная память"}:
                    visible.pop(key, None)
        if product.screen_size:
            for key in list(visible):
                if key.lower() in {"диагональ экрана", "экран"}:
                    visible.pop(key, None)
    return visible


@ensure_csrf_cookie
def home(request):
    featured_products = Product.objects.filter(is_active=True, is_featured=True).select_related("category").order_by("id")[:8]
    categories = Category.objects.filter(is_active=True).order_by("sort_order", "name")[:6]
    return render(
        request,
        "shop/home.html",
        {
            "featured_products": featured_products,
            "categories": categories,
        },
    )


@ensure_csrf_cookie
def catalog(request):
    return render(request, "shop/catalog.html")


@ensure_csrf_cookie
def product_detail(request, slug):
    product = get_object_or_404(Product.objects.select_related("category"), slug=slug, is_active=True)
    related = (
        Product.objects.filter(category=product.category, is_active=True)
        .exclude(id=product.id)
        .select_related("category")[:4]
    )
    return render(
        request,
        "shop/product_detail.html",
        {
            "product": product,
            "related_products": related,
            "visible_attributes": public_product_attributes(product.attributes, product),
        },
    )


@ensure_csrf_cookie
def cart_page(request):
    return render(request, "shop/cart.html")


@login_required
def account(request):
    if request.user.is_staff:
        return redirect("control_dashboard")
    return render(request, "shop/account.html")


def register(request):
    if request.user.is_authenticated:
        return redirect("account")
    if request.GET.get("reset") == "1":
        request.session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
        request.session.modified = True
        return redirect("register")
    pending_registration = request.session.get(PENDING_REGISTRATION_SESSION_KEY)
    form = RegisterForm(initial=pending_registration.get("data", {}) if pending_registration else None)
    show_verification_modal = bool(pending_registration)
    verification_error = ""

    if request.method == "POST" and request.POST.get("registration_step") == "verify":
        form, verification_error = verify_registration(request)
        if not verification_error and not form:
            return redirect("account")
        pending_registration = request.session.get(PENDING_REGISTRATION_SESSION_KEY)
        show_verification_modal = bool(pending_registration and verification_error)
    elif request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            pending_registration = store_pending_registration(request, form)
            form = RegisterForm(initial=pending_registration["data"])
            show_verification_modal = True

    return render(
        request,
        "registration/register.html",
        {
            "form": form,
            "show_verification_modal": show_verification_modal,
            "verification_error": verification_error,
            "verification_email": pending_registration.get("data", {}).get("email", "") if pending_registration else "",
            "verification_code": pending_registration.get("code", "") if pending_registration else "",
        },
    )


def store_pending_registration(request, form):
    data = {
        "username": form.cleaned_data["username"],
        "first_name": form.cleaned_data["first_name"],
        "email": form.cleaned_data["email"],
        "password1": form.cleaned_data["password1"],
        "password2": form.cleaned_data["password2"],
    }
    pending_registration = {
        "data": data,
        "code": f"{secrets.randbelow(1000000):06d}",
    }
    request.session[PENDING_REGISTRATION_SESSION_KEY] = pending_registration
    request.session.modified = True
    return pending_registration


def verify_registration(request):
    pending_registration = request.session.get(PENDING_REGISTRATION_SESSION_KEY)
    if not pending_registration:
        messages.error(request, "Сначала заполните форму регистрации.")
        return RegisterForm(request.POST), "Код подтверждения устарел."

    submitted_code = request.POST.get("verification_code", "").strip()
    expected_code = str(pending_registration.get("code", ""))
    form = RegisterForm(pending_registration.get("data", {}))
    if submitted_code != expected_code:
        return RegisterForm(initial=pending_registration.get("data", {})), "Неверный код подтверждения."
    if not form.is_valid():
        request.session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
        request.session.modified = True
        return form, "Данные регистрации устарели. Проверьте форму еще раз."

    user = form.save()
    CustomerProfile.objects.get_or_create(user=user)
    linked_count = link_guest_orders_to_user(request, user)
    request.session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
    request.session.modified = True
    login(request, user)
    if linked_count:
        messages.success(request, f"Аккаунт создан. В личный кабинет добавлено заказов: {linked_count}.")
    else:
        messages.success(request, "Аккаунт создан. История заказов будет храниться здесь.")
    return None, ""


def password_reset(request):
    if request.GET.get("reset") == "1":
        request.session.pop(PENDING_PASSWORD_RESET_SESSION_KEY, None)
        request.session.modified = True
        return redirect("password_reset")

    pending_reset = request.session.get(PENDING_PASSWORD_RESET_SESSION_KEY)
    request_form = PasswordResetRequestForm(initial={"email": pending_reset.get("email", "")} if pending_reset else None)
    confirm_form = PasswordResetConfirmForm()
    show_reset_modal = bool(pending_reset)
    reset_email = pending_reset.get("email", "") if pending_reset else ""
    reset_code = pending_reset.get("code", "") if pending_reset else ""
    reset_error = ""

    if request.method == "POST" and request.POST.get("password_reset_step") == "verify":
        confirm_form, reset_error = verify_password_reset(request)
        if not reset_error and not confirm_form:
            return redirect("login")
        pending_reset = request.session.get(PENDING_PASSWORD_RESET_SESSION_KEY)
        show_reset_modal = bool(pending_reset)
        reset_email = pending_reset.get("email", "") if pending_reset else reset_email
        reset_code = pending_reset.get("code", "") if pending_reset else reset_code
    elif request.method == "POST":
        request_form = PasswordResetRequestForm(request.POST)
        if request_form.is_valid():
            user = User.objects.filter(email__iexact=request_form.cleaned_data["email"]).order_by("id").first()
            if user:
                pending_reset = store_pending_password_reset(request, user, request_form.cleaned_data["email"])
                request_form = PasswordResetRequestForm(initial={"email": pending_reset["email"]})
                show_reset_modal = True
                reset_email = pending_reset["email"]
                reset_code = pending_reset["code"]
            else:
                request_form.add_error("email", "Пользователь с такой почтой не найден.")

    return render(
        request,
        "registration/password_reset.html",
        {
            "form": request_form,
            "confirm_form": confirm_form,
            "show_reset_modal": show_reset_modal,
            "reset_email": reset_email,
            "reset_code": reset_code,
            "reset_error": reset_error,
        },
    )


def store_pending_password_reset(request, user, email):
    pending_reset = {
        "email": email,
        "user_id": user.id,
        "code": f"{secrets.randbelow(1000000):06d}",
    }
    request.session[PENDING_PASSWORD_RESET_SESSION_KEY] = pending_reset
    request.session.modified = True
    return pending_reset


def verify_password_reset(request):
    pending_reset = request.session.get(PENDING_PASSWORD_RESET_SESSION_KEY)
    if not pending_reset:
        return PasswordResetConfirmForm(request.POST), "Код восстановления устарел."

    user = User.objects.filter(id=pending_reset.get("user_id")).first()
    if not user:
        request.session.pop(PENDING_PASSWORD_RESET_SESSION_KEY, None)
        request.session.modified = True
        return PasswordResetConfirmForm(request.POST), "Аккаунт не найден."

    confirm_form = PasswordResetConfirmForm(request.POST, user=user)
    submitted_code = request.POST.get("verification_code", "").strip()
    if submitted_code != str(pending_reset.get("code", "")):
        return confirm_form, "Неверный код подтверждения."
    if not confirm_form.is_valid():
        return confirm_form, ""

    user.set_password(confirm_form.cleaned_data["password2"])
    user.save(update_fields=["password"])
    request.session.pop(PENDING_PASSWORD_RESET_SESSION_KEY, None)
    request.session.modified = True
    messages.success(request, "Пароль обновлен. Войдите с новым паролем.")
    return None, ""


def checkout(request):
    snapshot = cart_snapshot(request.session)
    if not snapshot["items"]:
        messages.info(request, "Корзина пуста.")
        return redirect("cart")

    form = CheckoutForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            locked_products = {
                product.id: product
                for product in Product.objects.select_for_update().filter(
                    id__in=[cart_item["id"] for cart_item in snapshot["items"]]
                )
            }
            for cart_item in snapshot["items"]:
                product = locked_products.get(cart_item["id"])
                if not product or product.stock < cart_item["quantity"]:
                    messages.error(request, f"Недостаточно товара: {cart_item['name']}.")
                    return redirect("cart")

            order = Order.objects.create(
                user=request.user if request.user.is_authenticated else None,
                status=Order.Status.PAYMENT,
                payment_status=Order.PaymentStatus.WAITING,
                total=Decimal(str(snapshot["total"])),
                customer_name=form.cleaned_data["customer_name"],
                phone=form.cleaned_data["phone"],
                email=form.cleaned_data["email"],
            )

            for cart_item in snapshot["items"]:
                product = locked_products[cart_item["id"]]
                product.stock -= cart_item["quantity"]
                product.save(update_fields=["stock"])
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    product_name=product.name,
                    price=product.price,
                    quantity=cart_item["quantity"],
                )

            save_cart(request.session, {})
            if request.user.is_authenticated:
                sync_customer_profile_from_checkout(request.user, form.cleaned_data)

        if not request.user.is_authenticated:
            remember_guest_order(request, order)
        messages.success(request, "Заказ создан. Подтвердите демо-оплату.")
        return redirect("order_payment", order_number=order.order_number)

    return render(request, "shop/checkout.html", {"form": form, "cart": snapshot})


def sync_customer_profile_from_checkout(user, checkout_data):
    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    changed_fields = []
    phone = checkout_data.get("phone", "").strip()
    if phone and phone != profile.phone:
        profile.phone = phone
        changed_fields.append("phone")
    if changed_fields:
        profile.save(update_fields=changed_fields + ["updated_at"])


def remember_guest_order(request, order):
    order_ids = [int(order_id) for order_id in request.session.get(GUEST_ORDER_SESSION_KEY, [])]
    if order.id not in order_ids:
        order_ids.append(order.id)
    request.session[GUEST_ORDER_SESSION_KEY] = order_ids[-20:]
    request.session.modified = True


def link_guest_orders_to_user(request, user):
    email = (user.email or "").strip()
    if not email:
        return 0
    guest_order_ids = [int(order_id) for order_id in request.session.get(GUEST_ORDER_SESSION_KEY, [])]
    if not guest_order_ids:
        return 0
    linked_count = Order.objects.filter(
        id__in=guest_order_ids,
        user__isnull=True,
        email__iexact=email,
    ).update(user=user)
    if linked_count:
        remaining_ids = list(
            Order.objects.filter(
                id__in=guest_order_ids,
                user__isnull=True,
            ).values_list("id", flat=True)
        )
        if remaining_ids:
            request.session[GUEST_ORDER_SESSION_KEY] = remaining_ids
        else:
            request.session.pop(GUEST_ORDER_SESSION_KEY, None)
        request.session.modified = True
    return linked_count


def can_view_order(request, order):
    if request.user.is_authenticated and order.user_id == request.user.id:
        return True
    guest_order_ids = request.session.get(GUEST_ORDER_SESSION_KEY, [])
    return order.user_id is None and order.id in guest_order_ids


def order_detail(request, order_number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), order_number=order_number)
    if not can_view_order(request, order):
        raise Http404
    return render(request, "shop/order_detail.html", {"order": order})


def start_demo_payment(order):
    if order.payment_status in {Order.PaymentStatus.PAID, Order.PaymentStatus.PROCESSING}:
        return
    order.status = Order.Status.PAYMENT
    order.payment_status = Order.PaymentStatus.PROCESSING
    order.save(update_fields=["status", "payment_status"])
    try:
        process_order_payment.delay(order.id)
    except Exception:
        complete_demo_payment(order.id)


@require_http_methods(["GET", "POST"])
def order_payment(request, order_number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), order_number=order_number)
    if not can_view_order(request, order):
        raise Http404
    if order.payment_status in {Order.PaymentStatus.PAID, Order.PaymentStatus.PROCESSING}:
        return redirect("order_detail", order_number=order.order_number)
    if request.method == "POST":
        start_demo_payment(order)
        messages.success(request, "Демо-платеж принят в обработку.")
        return redirect("order_detail", order_number=order.order_number)
    return render(request, "shop/payment.html", {"order": order})


def parse_json(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def multi_value(params, name):
    values = params.getlist(name)
    if len(values) == 1 and "," in values[0]:
        values = values[0].split(",")
    return [value.strip() for value in values if value.strip()]


def parse_decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(" ", ""))
    except (InvalidOperation, TypeError):
        return None


def parse_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_positive_int(value, default, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    number = max(1, number)
    if maximum is not None:
        number = min(number, maximum)
    return number


def product_queryset_for_filters(params, exclude=()):
    exclude = set(exclude)
    products = Product.objects.filter(is_active=True).select_related("category")

    query = params.get("q", "").strip()
    if query and "q" not in exclude:
        products = products.filter(
            Q(name__icontains=query)
            | Q(brand__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
        )

    category = params.get("category")
    if category and "category" not in exclude:
        products = products.filter(category__slug=category)

    brands = multi_value(params, "brand")
    if brands and "brand" not in exclude:
        products = products.filter(brand__in=brands)

    colors = multi_value(params, "color")
    if colors and "color" not in exclude:
        products = products.filter(color__in=colors)

    memories = multi_value(params, "memory")
    if memories and "memory" not in exclude:
        products = products.filter(memory__in=memories)

    price_min = parse_decimal(params.get("price_min"))
    price_max = parse_decimal(params.get("price_max"))
    if price_min is not None and "price" not in exclude:
        products = products.filter(price__gte=price_min)
    if price_max is not None and "price" not in exclude:
        products = products.filter(price__lte=price_max)

    if params.get("in_stock") == "1" and "in_stock" not in exclude:
        products = products.filter(stock__gt=0)

    return products


def filtered_products(params):
    products = product_queryset_for_filters(params)
    sort = params.get("sort", "featured")
    if sort == "price_asc":
        return products.order_by("price", "name")
    if sort == "price_desc":
        return products.order_by("-price", "name")
    if sort == "newest":
        return products.order_by("-created_at", "name")
    return products.order_by("-is_featured", "id")


def serialize_product(product):
    return {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "url": product.get_absolute_url(),
        "category": product.category.name,
        "category_slug": product.category.slug,
        "brand": product.brand,
        "description": product.description,
        "price": float(product.price),
        "price_display": money(product.price),
        "old_price": float(product.old_price) if product.old_price else None,
        "old_price_display": money(product.old_price) if product.old_price else "",
        "discount_percent": product.discount_percent,
        "image": product_static_url(product.image),
        "stock": product.stock,
        "in_stock": product.in_stock,
        "color": product.color,
        "memory": product.memory,
        "screen_size": product.screen_size,
        "attributes": public_product_attributes(product.attributes, product),
    }


@require_GET
def api_products(request):
    per_page = parse_positive_int(request.GET.get("per_page"), 24, maximum=48)
    requested_page = parse_positive_int(request.GET.get("page"), 1)
    paginator = Paginator(filtered_products(request.GET), per_page)
    page_obj = paginator.get_page(requested_page)
    products = list(page_obj.object_list)
    return JsonResponse(
        {
            "products": [serialize_product(product) for product in products],
            "count": paginator.count,
            "page_count": len(products),
            "pagination": {
                "page": page_obj.number,
                "pages": paginator.num_pages,
                "per_page": per_page,
                "total": paginator.count,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
                "previous_page": page_obj.previous_page_number() if page_obj.has_previous() else None,
            },
        }
    )


def merge_selected_options(options, selected):
    result = list(options)
    for item in selected:
        if item and item not in result:
            result.append(item)
    return result


def facet_values(params, field, exclude):
    products = product_queryset_for_filters(params, exclude={exclude})
    values = products.exclude(**{field: ""}).order_by(field).values_list(field, flat=True).distinct()
    return list(values)


@require_GET
def api_catalog_meta(request):
    category_products = product_queryset_for_filters(request.GET, exclude={"category"})
    price_products = product_queryset_for_filters(request.GET, exclude={"price"})
    price_range = price_products.aggregate(min=Min("price"), max=Max("price"))
    category_options = [
        {"name": item["category__name"], "slug": item["category__slug"]}
        for item in (
            category_products.values("category__name", "category__slug", "category__sort_order")
            .order_by("category__sort_order", "category__name")
            .distinct()
        )
    ]
    selected_category = request.GET.get("category", "")
    if selected_category and selected_category not in {item["slug"] for item in category_options}:
        category = Category.objects.filter(slug=selected_category, is_active=True).first()
        if category:
            category_options.append({"name": category.name, "slug": category.slug})

    return JsonResponse(
        {
            "categories": category_options,
            "brands": merge_selected_options(
                facet_values(request.GET, "brand", "brand"),
                multi_value(request.GET, "brand"),
            ),
            "colors": merge_selected_options(
                facet_values(request.GET, "color", "color"),
                multi_value(request.GET, "color"),
            ),
            "memories": merge_selected_options(
                facet_values(request.GET, "memory", "memory"),
                multi_value(request.GET, "memory"),
            ),
            "price_min": int(price_range["min"] or 0),
            "price_max": int(price_range["max"] or 0),
        }
    )


@require_http_methods(["GET", "POST", "PATCH", "DELETE"])
def api_cart(request):
    if request.method == "GET":
        payload = cart_snapshot(request.session)
        payload["checkout_url"] = reverse("checkout")
        return JsonResponse(payload)

    data = parse_json(request)
    product_id = str(data.get("product_id", "")).strip()
    quantity = parse_int(data.get("quantity"), 1)

    product = get_object_or_404(Product, id=product_id, is_active=True)
    cart = get_cart(request.session)

    if request.method == "POST":
        if product.stock <= 0:
            return JsonResponse({"detail": "Товар скоро в продаже"}, status=409)
        current = cart.get(product_id, 0)
        cart[product_id] = min(product.stock, current + max(quantity, 1))
    elif request.method == "PATCH":
        if quantity <= 0:
            cart.pop(product_id, None)
        else:
            cart[product_id] = min(product.stock, quantity)
    elif request.method == "DELETE":
        cart.pop(product_id, None)

    save_cart(request.session, cart)
    payload = cart_snapshot(request.session)
    payload["checkout_url"] = reverse("checkout")
    return JsonResponse(payload)


def api_login_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "auth_required", "login_url": reverse("login")}, status=401)
        return view_func(request, *args, **kwargs)

    return wrapper


def get_customer_profile(user):
    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    return profile


def clean_text(value, max_length):
    return str(value or "").strip()[:max_length]


def account_payload(user):
    profile = get_customer_profile(user)
    orders = user.orders.prefetch_related("items").order_by("-created_at")
    paid_total = orders.filter(payment_status=Order.PaymentStatus.PAID).aggregate(total=Sum("total"))["total"] or Decimal("0")
    active_orders_count = orders.exclude(status__in=[Order.Status.READY, Order.Status.CANCELLED]).count()
    last_order = orders.first()
    return {
        "user": {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "name": user.get_full_name() or user.username,
            "email": user.email,
            "phone": profile.phone,
            "city": profile.city,
            "address": profile.address,
            "marketing_consent": profile.marketing_consent,
            "date_joined": user.date_joined.strftime("%d.%m.%Y"),
        },
        "stats": {
            "orders_count": orders.count(),
            "active_orders_count": active_orders_count,
            "paid_total_display": money(paid_total),
            "last_order_number": last_order.order_number if last_order else "",
            "last_order_date": last_order.created_at.strftime("%d.%m.%Y") if last_order else "",
        },
        "orders": [serialize_account_order(order) for order in orders],
    }


def serialize_account_order(order):
    return {
        "id": order.id,
        "number": order.order_number,
        "url": reverse("order_detail", args=[order.order_number]),
        "payment_url": reverse("order_payment", args=[order.order_number]),
        "status": order.status,
        "status_label": order.get_status_display(),
        "payment_status": order.payment_status,
        "payment_label": order.get_payment_status_display(),
        "total_display": money(order.total),
        "created_at": order.created_at.strftime("%d.%m.%Y %H:%M"),
        "paid_at": order.paid_at.strftime("%d.%m.%Y %H:%M") if order.paid_at else "",
        "pickup_code": order.pickup_code,
        "qr_svg": order.qr_svg if order.is_ready else "",
        "items": [
            {
                "name": item.product_name,
                "quantity": item.quantity,
                "price_display": money(item.price),
                "line_total_display": money(item.line_total),
            }
            for item in order.items.all()
        ],
    }


def update_account_profile(request):
    data = parse_json(request)
    errors = {}

    first_name = clean_text(data.get("first_name"), 80)
    last_name = clean_text(data.get("last_name"), 150)
    email = clean_text(data.get("email"), 254)
    phone = clean_text(data.get("phone"), 40)
    city = clean_text(data.get("city"), 120)
    address = clean_text(data.get("address"), 220)
    marketing_consent = bool(data.get("marketing_consent"))

    if not first_name:
        errors["first_name"] = "Укажите имя."
    if not email:
        errors["email"] = "Укажите email."
    else:
        try:
            validate_email(email)
        except ValidationError:
            errors["email"] = "Некорректный email."
        if User.objects.filter(email__iexact=email).exclude(id=request.user.id).exists():
            errors["email"] = "Этот email уже используется."
    if phone and len(phone) < 6:
        errors["phone"] = "Телефон слишком короткий."

    if errors:
        return JsonResponse({"errors": errors}, status=400)

    request.user.first_name = first_name
    request.user.last_name = last_name
    request.user.email = email
    request.user.save(update_fields=["first_name", "last_name", "email"])

    profile = get_customer_profile(request.user)
    profile.phone = phone
    profile.city = city
    profile.address = address
    profile.marketing_consent = marketing_consent
    profile.save(update_fields=["phone", "city", "address", "marketing_consent", "updated_at"])

    return JsonResponse(account_payload(request.user))


@require_http_methods(["GET", "PATCH"])
@api_login_required
def api_account(request):
    if request.user.is_staff:
        return JsonResponse(
            {"detail": "staff_users_use_control", "control_url": reverse("control_dashboard")},
            status=403,
        )
    if request.method == "PATCH":
        return update_account_profile(request)
    return JsonResponse(account_payload(request.user))
