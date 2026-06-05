from datetime import timedelta
from decimal import Decimal
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .admin_access import control_nav_for, get_staff_profile, has_control_access, role_capability_rows, user_can
from .forms import (
    AdminCategoryForm,
    AdminProductForm,
    AdminStaffProfileForm,
    AdminUserCreateForm,
    SiteContentForm,
)
from .models import Category, Order, OrderItem, PageView, Product, SiteContent, StaffProfile
from .views_cart import money


User = get_user_model()


def money_display(value):
    return f"{money(value or Decimal('0'))} ₽"


def line_total_expression():
    return ExpressionWrapper(F("price") * F("quantity"), output_field=DecimalField(max_digits=14, decimal_places=2))


def control_context(request, active_name, **extra):
    profile = get_staff_profile(request.user)
    context = {
        "control_nav": control_nav_for(request.user, active_name),
        "control_profile": profile,
        "control_role": "Суперпользователь" if request.user.is_superuser else (profile.get_role_display() if profile else ""),
        "service_mode_open": service_mode_available(),
    }
    context.update(extra)
    return context


def login_redirect(request):
    return redirect(f"{reverse('login')}?{urlencode({'next': request.get_full_path()})}")


def forbidden(request, active_name="control_dashboard"):
    return render(
        request,
        "control/forbidden.html",
        control_context(request, active_name),
        status=403,
    )


def control_required(permission="dashboard"):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return login_redirect(request)
            if not has_control_access(request.user) or not user_can(request.user, permission):
                return forbidden(request, kwargs.get("active_name", "control_dashboard"))
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def service_mode_available():
    return bool(getattr(settings, "CONTROL_SERVICE_MODE", False)) or not StaffProfile.objects.filter(is_active=True).exists()


def add_percent(rows, value_key="count"):
    rows = list(rows)
    max_value = max([row.get(value_key) or 0 for row in rows] or [0])
    for row in rows:
        value = row.get(value_key) or 0
        row["percent"] = round((float(value) / float(max_value)) * 100) if max_value else 0
    return rows


def unique_sessions(queryset):
    return queryset.exclude(session_key="").values("session_key").distinct().count()


@control_required("dashboard")
def dashboard(request):
    now = timezone.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_week = now - timedelta(days=7)

    paid_orders = Order.objects.filter(payment_status=Order.PaymentStatus.PAID)
    revenue = paid_orders.aggregate(total=Sum("total"))["total"] or Decimal("0")
    week_revenue = paid_orders.filter(paid_at__gte=last_week).aggregate(total=Sum("total"))["total"] or Decimal("0")
    public_views_week = PageView.objects.filter(created_at__gte=last_week, is_staff_area=False)
    sessions_week = unique_sessions(public_views_week)
    order_sessions_week = unique_sessions(public_views_week.filter(path__startswith="/orders/"))
    conversion = f"{(order_sessions_week / sessions_week * 100):.1f}%" if sessions_week else "0%"

    metrics = [
        {
            "label": "Выручка",
            "value": money_display(revenue),
            "hint": f"За 7 дней: {money_display(week_revenue)}",
            "icon": "badge-russian-ruble",
        },
        {
            "label": "Заказы",
            "value": Order.objects.count(),
            "hint": f"Сегодня: {Order.objects.filter(created_at__gte=today).count()}",
            "icon": "receipt-text",
        },
        {
            "label": "Товары",
            "value": Product.objects.count(),
            "hint": f"Скоро в продаже: {Product.objects.filter(stock=0).count()}",
            "icon": "package",
        },
        {
            "label": "Конверсия",
            "value": conversion,
            "hint": f"Сессий с заказом: {order_sessions_week} из {sessions_week}",
            "icon": "chart-no-axes-combined",
        },
    ]

    return render(
        request,
        "control/dashboard.html",
        control_context(
            request,
            "control_dashboard",
            metrics=metrics,
            recent_orders=Order.objects.prefetch_related("items").order_by("-created_at")[:8],
            low_stock_products=Product.objects.filter(is_active=True, stock__lte=3).select_related("category").order_by("stock", "name")[:8],
            top_pages=add_percent(
                PageView.objects.filter(created_at__gte=last_week, is_staff_area=False)
                .values("path")
                .annotate(count=Count("id"))
                .order_by("-count")[:6]
            ),
            can_manage_staff=user_can(request.user, "staff"),
        ),
    )


@control_required("products")
def products(request):
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    stock = request.GET.get("stock", "").strip()
    products_qs = Product.objects.select_related("category").order_by("-created_at", "name")
    if query:
        products_qs = products_qs.filter(Q(name__icontains=query) | Q(brand__icontains=query) | Q(slug__icontains=query))
    if category:
        products_qs = products_qs.filter(category__slug=category)
    if stock == "empty":
        products_qs = products_qs.filter(stock=0)
    elif stock == "low":
        products_qs = products_qs.filter(stock__gt=0, stock__lte=3)

    paginator = Paginator(products_qs, 24)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "control/products.html",
        control_context(
            request,
            "control_products",
            page_obj=page_obj,
            products=page_obj.object_list,
            categories=Category.objects.order_by("sort_order", "name"),
            total_count=products_qs.count(),
            current_category=category,
            current_stock=stock,
            query=query,
        ),
    )


@control_required("products")
@require_http_methods(["GET", "POST"])
def product_form(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    form = AdminProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        messages.success(request, "Товар сохранен.")
        return redirect("control_product_edit", pk=product.pk)
    return render(
        request,
        "control/product_form.html",
        control_context(
            request,
            "control_products",
            form=form,
            product=product,
            title="Новый товар" if product is None else "Редактирование товара",
        ),
    )


@control_required("products")
def categories(request):
    return render(
        request,
        "control/categories.html",
        control_context(
            request,
            "control_products",
            categories=Category.objects.annotate(products_count=Count("products")).order_by("sort_order", "name"),
        ),
    )


@control_required("products")
@require_http_methods(["GET", "POST"])
def category_form(request, pk=None):
    category = get_object_or_404(Category, pk=pk) if pk else None
    form = AdminCategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        category = form.save()
        messages.success(request, "Категория сохранена.")
        return redirect("control_category_edit", pk=category.pk)
    return render(
        request,
        "control/category_form.html",
        control_context(
            request,
            "control_products",
            form=form,
            category=category,
            title="Новая категория" if category is None else "Редактирование категории",
        ),
    )


@control_required("content")
def content(request):
    return render(
        request,
        "control/content.html",
        control_context(
            request,
            "control_content",
            blocks=SiteContent.objects.select_related("updated_by").order_by("block_type", "key"),
        ),
    )


@control_required("content")
@require_http_methods(["GET", "POST"])
def content_form(request, pk=None):
    block = get_object_or_404(SiteContent, pk=pk) if pk else None
    form = SiteContentForm(request.POST or None, instance=block)
    if request.method == "POST" and form.is_valid():
        block = form.save(commit=False)
        block.updated_by = request.user
        block.save()
        messages.success(request, "Контентный блок сохранен.")
        return redirect("control_content_edit", pk=block.pk)
    return render(
        request,
        "control/content_form.html",
        control_context(
            request,
            "control_content",
            form=form,
            block=block,
            title="Новый блок" if block is None else "Редактирование блока",
        ),
    )


@control_required("orders")
def orders(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    payment = request.GET.get("payment", "").strip()
    orders_qs = Order.objects.prefetch_related("items").select_related("user").order_by("-created_at")
    if query:
        orders_qs = orders_qs.filter(
            Q(order_number__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
            | Q(customer_name__icontains=query)
        )
    if status:
        orders_qs = orders_qs.filter(status=status)
    if payment:
        orders_qs = orders_qs.filter(payment_status=payment)

    paginator = Paginator(orders_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "control/orders.html",
        control_context(
            request,
            "control_orders",
            page_obj=page_obj,
            orders=page_obj.object_list,
            query=query,
            current_status=status,
            current_payment=payment,
            statuses=Order.Status.choices,
            payment_statuses=Order.PaymentStatus.choices,
            total_count=orders_qs.count(),
        ),
    )


@control_required("users")
def users(request):
    query = request.GET.get("q", "").strip()
    users_qs = User.objects.select_related("customer_profile").annotate(
        orders_count=Count("orders", distinct=True),
        paid_total=Sum("orders__total", filter=Q(orders__payment_status=Order.PaymentStatus.PAID)),
    ).order_by("-date_joined")
    if query:
        users_qs = users_qs.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
    paginator = Paginator(users_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    user_rows = [
        {
            "user": user,
            "phone": getattr(getattr(user, "customer_profile", None), "phone", ""),
            "orders_count": user.orders_count,
            "paid_total_display": money_display(user.paid_total),
            "last_order": user.orders.order_by("-created_at").first(),
        }
        for user in page_obj.object_list
    ]
    return render(
        request,
        "control/users.html",
        control_context(
            request,
            "control_users",
            page_obj=page_obj,
            user_rows=user_rows,
            query=query,
            total_count=users_qs.count(),
        ),
    )


@control_required("analytics")
def analytics(request):
    paid_orders = Order.objects.filter(payment_status=Order.PaymentStatus.PAID)
    paid_revenue = paid_orders.aggregate(total=Sum("total"))["total"] or Decimal("0")
    average_order = paid_orders.aggregate(total=Sum("total"), count=Count("id"))
    average_value = average_order["total"] / average_order["count"] if average_order["count"] else Decimal("0")
    repeat_customers = (
        User.objects.annotate(orders_count=Count("orders"))
        .filter(orders_count__gt=1)
        .count()
    )

    order_status_rows = add_percent(
        Order.objects.values("status").annotate(count=Count("id")).order_by("-count")
    )
    for row in order_status_rows:
        row["label"] = dict(Order.Status.choices).get(row["status"], row["status"])

    payment_rows = add_percent(
        Order.objects.values("payment_status").annotate(count=Count("id")).order_by("-count")
    )
    for row in payment_rows:
        row["label"] = dict(Order.PaymentStatus.choices).get(row["payment_status"], row["payment_status"])

    category_rows = add_percent(
        OrderItem.objects.filter(order__payment_status=Order.PaymentStatus.PAID, product__category__isnull=False)
        .values("product__category__name")
        .annotate(total=Sum(line_total_expression()), count=Count("id"))
        .order_by("-total")[:10],
        "total",
    )
    for row in category_rows:
        row["label"] = row["product__category__name"] or "Без категории"
        row["total_display"] = money_display(row["total"])

    brand_rows = add_percent(
        OrderItem.objects.filter(order__payment_status=Order.PaymentStatus.PAID, product__isnull=False)
        .values("product__brand")
        .annotate(total=Sum(line_total_expression()), quantity=Sum("quantity"))
        .order_by("-total")[:10],
        "total",
    )
    for row in brand_rows:
        row["label"] = row["product__brand"] or "Без бренда"
        row["total_display"] = money_display(row["total"])

    system_metrics = [
        {"label": "Оплаченная выручка", "value": money_display(paid_revenue), "hint": "Только успешные демо-платежи"},
        {"label": "Средний чек", "value": money_display(average_value), "hint": "По оплаченным заказам"},
        {"label": "Повторные покупатели", "value": repeat_customers, "hint": "Пользователи с 2+ заказами"},
        {"label": "Остаток товаров", "value": Product.objects.aggregate(total=Sum("stock"))["total"] or 0, "hint": "Сумма остатков на складе"},
    ]

    return render(
        request,
        "control/analytics.html",
        control_context(
            request,
            "control_analytics",
            system_metrics=system_metrics,
            order_status_rows=order_status_rows,
            payment_rows=payment_rows,
            category_rows=category_rows,
            brand_rows=brand_rows,
            low_stock_products=Product.objects.filter(stock__lte=3).select_related("category").order_by("stock", "name")[:15],
        ),
    )


@control_required("analytics")
def web_analytics(request):
    try:
        days = int(request.GET.get("days", "7"))
    except ValueError:
        days = 7
    days = days if days in {7, 30, 90} else 7
    since = timezone.now() - timedelta(days=days)
    views_qs = PageView.objects.filter(created_at__gte=since)
    public_views = views_qs.filter(is_staff_area=False)

    daily_rows = list(
        public_views.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    daily_rows = add_percent(daily_rows)
    for row in daily_rows:
        row["label"] = row["day"].strftime("%d.%m") if row["day"] else ""

    top_pages = add_percent(
        public_views.values("path").annotate(count=Count("id"), unique=Count("session_key", distinct=True)).order_by("-count")[:12]
    )
    referrers = add_percent(
        public_views.exclude(referrer="")
        .values("referrer")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    device_rows = add_percent(
        public_views.values("device").annotate(count=Count("id")).order_by("-count")
    )
    for row in device_rows:
        row["label"] = {"desktop": "Desktop", "mobile": "Mobile", "tablet": "Tablet"}.get(row["device"], "Неизвестно")

    staff_views = views_qs.filter(is_staff_area=True).count()
    web_metrics = [
        {"label": "Просмотры", "value": public_views.count(), "hint": f"Публичные страницы за {days} дней"},
        {"label": "Уникальные сессии", "value": unique_sessions(public_views), "hint": "По session key"},
        {"label": "Staff-area просмотры", "value": staff_views, "hint": "Раздел /control/"},
        {"label": "Ошибки 4xx/5xx", "value": views_qs.filter(status_code__gte=400).count(), "hint": "По статусам ответа"},
    ]

    return render(
        request,
        "control/web_analytics.html",
        control_context(
            request,
            "control_web_analytics",
            days=days,
            web_metrics=web_metrics,
            daily_rows=daily_rows,
            top_pages=top_pages,
            referrers=referrers,
            device_rows=device_rows,
            recent_views=PageView.objects.select_related("user").order_by("-created_at")[:30],
        ),
    )


@control_required("staff")
def staff(request):
    return render(
        request,
        "control/staff.html",
        control_context(
            request,
            "control_staff",
            profiles=StaffProfile.objects.select_related("user").order_by("role", "user__username"),
            role_rows=role_capability_rows(),
        ),
    )


@control_required("staff")
@require_http_methods(["GET", "POST"])
def staff_create(request):
    form = AdminUserCreateForm(request.POST or None, initial={"role": StaffProfile.Role.ADMIN})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
        messages.success(request, "Пользователь админки создан.")
        return redirect("control_staff")
    return render(
        request,
        "control/staff_create.html",
        control_context(
            request,
            "control_staff",
            form=form,
            role_rows=role_capability_rows(),
        ),
    )


@control_required("staff")
@require_http_methods(["GET", "POST"])
def staff_edit(request, pk):
    profile = get_object_or_404(StaffProfile.objects.select_related("user"), pk=pk)
    form = AdminStaffProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Профиль админки обновлен.")
        return redirect("control_staff")
    return render(
        request,
        "control/staff_form.html",
        control_context(request, "control_staff", form=form, profile=profile, title="Редактирование роли"),
    )


@require_http_methods(["GET", "POST"])
def service(request):
    service_open = service_mode_available()
    privileged_user = request.user.is_authenticated and user_can(request.user, "staff")
    if not service_open and not privileged_user:
        if not request.user.is_authenticated:
            return login_redirect(request)
        return forbidden(request, "control_staff")

    initial_role = StaffProfile.Role.OWNER if not StaffProfile.objects.exists() else StaffProfile.Role.ADMIN
    form = AdminUserCreateForm(request.POST or None, initial={"role": initial_role})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
        messages.success(request, "Пользователь админки создан.")
        if privileged_user:
            return redirect("control_staff")
        login(request, user)
        return redirect("control_dashboard")

    return render(
        request,
        "control/service.html",
        control_context(
            request,
            "control_staff",
            form=form,
            service_open=service_open,
            initial_role=initial_role,
            role_rows=role_capability_rows(),
        ),
    )
