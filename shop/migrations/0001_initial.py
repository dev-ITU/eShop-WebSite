import django.db.models.deletion
import shop.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=140, unique=True)),
                ("description", models.TextField(blank=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "категория",
                "verbose_name_plural": "категории",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order_number", models.CharField(default=shop.models.make_order_number, max_length=32, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "Новый"),
                            ("payment", "Оплата"),
                            ("paid", "Оплачен"),
                            ("ready", "Готов к выдаче"),
                            ("cancelled", "Отменен"),
                        ],
                        default="new",
                        max_length=20,
                    ),
                ),
                (
                    "payment_status",
                    models.CharField(
                        choices=[
                            ("waiting", "Ожидает"),
                            ("processing", "В обработке"),
                            ("paid", "Оплачен"),
                            ("failed", "Ошибка"),
                        ],
                        default="waiting",
                        max_length=20,
                    ),
                ),
                ("total", models.DecimalField(decimal_places=2, max_digits=12)),
                ("customer_name", models.CharField(max_length=160)),
                ("phone", models.CharField(max_length=40)),
                ("email", models.EmailField(max_length=254)),
                ("pickup_code", models.CharField(default=shop.models.make_pickup_code, max_length=12)),
                ("qr_svg", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("ready_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="orders", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                "verbose_name": "заказ",
                "verbose_name_plural": "заказы",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=220)),
                ("slug", models.SlugField(blank=True, max_length=240, unique=True)),
                ("brand", models.CharField(db_index=True, max_length=100)),
                ("description", models.TextField()),
                ("price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("old_price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("image", models.CharField(blank=True, max_length=255)),
                ("stock", models.PositiveIntegerField(default=0)),
                ("color", models.CharField(blank=True, db_index=True, max_length=80)),
                ("memory", models.CharField(blank=True, db_index=True, max_length=80)),
                ("screen_size", models.CharField(blank=True, max_length=40)),
                ("attributes", models.JSONField(blank=True, default=dict)),
                ("is_featured", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "category",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="products", to="shop.category"),
                ),
            ],
            options={
                "verbose_name": "товар",
                "verbose_name_plural": "товары",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product_name", models.CharField(max_length=220)),
                ("price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("quantity", models.PositiveIntegerField(default=1)),
                (
                    "order",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="shop.order"),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="shop.product",
                    ),
                ),
            ],
            options={
                "verbose_name": "позиция заказа",
                "verbose_name_plural": "позиции заказа",
            },
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["brand", "color"], name="product_brand_color_idx"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["price"], name="product_price_idx"),
        ),
    ]
