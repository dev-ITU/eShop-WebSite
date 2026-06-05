import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


def make_order_number():
    return f"BGX-{timezone.now():%y%m%d}-{secrets.token_hex(3).upper()}"


def make_pickup_code():
    return secrets.token_urlsafe(8).replace("-", "").replace("_", "").upper()[:8]


class Category(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "категория"
        verbose_name_plural = "категории"

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(Category, related_name="products", on_delete=models.PROTECT)
    name = models.CharField(max_length=220)
    slug = models.SlugField(max_length=240, unique=True, blank=True)
    brand = models.CharField(max_length=100, db_index=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    old_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    image = models.CharField(max_length=255, blank=True)
    stock = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=80, blank=True, db_index=True)
    memory = models.CharField(max_length=80, blank=True, db_index=True)
    screen_size = models.CharField(max_length=40, blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["brand", "color"], name="product_brand_color_idx"),
            models.Index(fields=["price"], name="product_price_idx"),
        ]
        verbose_name = "товар"
        verbose_name_plural = "товары"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("product_detail", kwargs={"slug": self.slug})

    @property
    def discount_percent(self):
        if not self.old_price or self.old_price <= self.price:
            return 0
        return round((self.old_price - self.price) / self.old_price * 100)

    @property
    def in_stock(self):
        return self.stock > 0


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новый"
        PAYMENT = "payment", "Оплата"
        PAID = "paid", "Оплачен"
        READY = "ready", "Готов к выдаче"
        CANCELLED = "cancelled", "Отменен"

    class PaymentStatus(models.TextChoices):
        WAITING = "waiting", "Ожидает"
        PROCESSING = "processing", "В обработке"
        PAID = "paid", "Оплачен"
        FAILED = "failed", "Ошибка"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="orders",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    order_number = models.CharField(max_length=32, unique=True, default=make_order_number)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.WAITING,
    )
    total = models.DecimalField(max_digits=12, decimal_places=2)
    customer_name = models.CharField(max_length=160)
    phone = models.CharField(max_length=40)
    email = models.EmailField()
    pickup_code = models.CharField(max_length=12, default=make_pickup_code)
    qr_svg = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "заказ"
        verbose_name_plural = "заказы"

    def __str__(self):
        return self.order_number

    @property
    def is_ready(self):
        return self.status == self.Status.READY and bool(self.qr_svg)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL)
    product_name = models.CharField(max_length=220)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "позиция заказа"
        verbose_name_plural = "позиции заказа"

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    @property
    def line_total(self):
        return self.price * self.quantity


class CustomerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="customer_profile", on_delete=models.CASCADE)
    phone = models.CharField(max_length=40, blank=True)
    city = models.CharField(max_length=120, blank=True)
    address = models.CharField(max_length=220, blank=True)
    marketing_consent = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]
        verbose_name = "профиль покупателя"
        verbose_name_plural = "профили покупателей"

    def __str__(self):
        return f"Профиль {self.user}"


class StaffProfile(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Владелец"
        ADMIN = "admin", "Администратор"
        MANAGER = "manager", "Оператор заказов"
        CONTENT = "content", "Контент-менеджер"
        ANALYST = "analyst", "Аналитик"
        SUPPORT = "support", "Поддержка"

    ROLE_CAPABILITIES = {
        Role.OWNER: {"dashboard", "products", "content", "orders", "users", "analytics", "staff"},
        Role.ADMIN: {"dashboard", "products", "content", "orders", "users", "analytics"},
        Role.MANAGER: {"dashboard", "orders", "users"},
        Role.CONTENT: {"dashboard", "products", "content"},
        Role.ANALYST: {"dashboard", "analytics", "users"},
        Role.SUPPORT: {"dashboard", "orders", "users"},
    }

    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="staff_profile", on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MANAGER)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]
        verbose_name = "профиль админки"
        verbose_name_plural = "профили админки"

    def __str__(self):
        return f"{self.user} - {self.get_role_display()}"

    def can(self, permission):
        return self.is_active and permission in self.ROLE_CAPABILITIES.get(self.role, set())


class SiteContent(models.Model):
    class BlockType(models.TextChoices):
        TEXT = "text", "Текст"
        HERO = "hero", "Баннер"
        NOTICE = "notice", "Уведомление"
        FOOTER = "footer", "Подвал"

    key = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    block_type = models.CharField(max_length=20, choices=BlockType.choices, default=BlockType.TEXT)
    is_active = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_content_blocks",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["block_type", "key"]
        verbose_name = "контентный блок"
        verbose_name_plural = "контентные блоки"

    def __str__(self):
        return self.title


class PageView(models.Model):
    path = models.CharField(max_length=260, db_index=True)
    full_path = models.TextField(blank=True)
    method = models.CharField(max_length=12, default="GET")
    status_code = models.PositiveSmallIntegerField(default=200)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    referrer = models.TextField(blank=True)
    device = models.CharField(max_length=20, blank=True, db_index=True)
    is_staff_area = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at", "path"], name="pageview_created_path_idx"),
            models.Index(fields=["created_at", "device"], name="pageview_created_device_idx"),
        ]
        verbose_name = "просмотр страницы"
        verbose_name_plural = "просмотры страниц"

    def __str__(self):
        return f"{self.path} {self.status_code}"
