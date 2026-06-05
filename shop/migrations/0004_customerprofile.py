from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_customer_profiles(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    CustomerProfile = apps.get_model("shop", "CustomerProfile")
    existing_user_ids = set(CustomerProfile.objects.values_list("user_id", flat=True))
    CustomerProfile.objects.bulk_create(
        [CustomerProfile(user_id=user_id) for user_id in User.objects.values_list("id", flat=True) if user_id not in existing_user_ids]
    )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("shop", "0003_custom_admin_analytics"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("city", models.CharField(blank=True, max_length=120)),
                ("address", models.CharField(blank=True, max_length=220)),
                ("marketing_consent", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="customer_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "профиль покупателя",
                "verbose_name_plural": "профили покупателей",
                "ordering": ["user__username"],
            },
        ),
        migrations.RunPython(create_customer_profiles, migrations.RunPython.noop),
    ]
