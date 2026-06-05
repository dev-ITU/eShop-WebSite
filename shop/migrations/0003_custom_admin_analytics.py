from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_default_content(apps, schema_editor):
    SiteContent = apps.get_model("shop", "SiteContent")
    defaults = [
        {
            "key": "footer_order",
            "title": "Заказ",
            "block_type": "footer",
            "body": "Оплата имитируется внутри проекта. После оформления заказ появляется в личном кабинете вместе с QR-кодом получения.",
        },
        {
            "key": "payment_notice",
            "title": "Демо-оплата",
            "block_type": "notice",
            "body": "Платежная форма не списывает деньги и нужна только для демонстрации сценария заказа.",
        },
        {
            "key": "home_catalog_note",
            "title": "Каталог",
            "block_type": "text",
            "body": "Каталог гаджетов с фильтрами, корзиной, демо-оплатой и QR-кодом для получения заказа.",
        },
    ]
    for item in defaults:
        SiteContent.objects.get_or_create(key=item["key"], defaults=item)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("shop", "0002_allow_guest_orders"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteContent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(max_length=80, unique=True)),
                ("title", models.CharField(max_length=160)),
                ("body", models.TextField(blank=True)),
                (
                    "block_type",
                    models.CharField(
                        choices=[
                            ("text", "Текст"),
                            ("hero", "Баннер"),
                            ("notice", "Уведомление"),
                            ("footer", "Подвал"),
                        ],
                        default="text",
                        max_length=20,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_content_blocks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "контентный блок",
                "verbose_name_plural": "контентные блоки",
                "ordering": ["block_type", "key"],
            },
        ),
        migrations.CreateModel(
            name="StaffProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Владелец"),
                            ("admin", "Администратор"),
                            ("manager", "Оператор заказов"),
                            ("content", "Контент-менеджер"),
                            ("analyst", "Аналитик"),
                            ("support", "Поддержка"),
                        ],
                        default="manager",
                        max_length=20,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "профиль админки",
                "verbose_name_plural": "профили админки",
                "ordering": ["user__username"],
            },
        ),
        migrations.CreateModel(
            name="PageView",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("path", models.CharField(db_index=True, max_length=260)),
                ("full_path", models.TextField(blank=True)),
                ("method", models.CharField(default="GET", max_length=12)),
                ("status_code", models.PositiveSmallIntegerField(default=200)),
                ("session_key", models.CharField(blank=True, db_index=True, max_length=40)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("referrer", models.TextField(blank=True)),
                ("device", models.CharField(blank=True, db_index=True, max_length=20)),
                ("is_staff_area", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "просмотр страницы",
                "verbose_name_plural": "просмотры страниц",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="pageview",
            index=models.Index(fields=["created_at", "path"], name="pageview_created_path_idx"),
        ),
        migrations.AddIndex(
            model_name="pageview",
            index=models.Index(fields=["created_at", "device"], name="pageview_created_device_idx"),
        ),
        migrations.RunPython(create_default_content, migrations.RunPython.noop),
    ]
