from django.urls import reverse

from .models import StaffProfile


CONTROL_NAV = [
    ("dashboard", "control_dashboard", "layout-dashboard", "Обзор"),
    ("products", "control_products", "package", "Товары"),
    ("content", "control_content", "file-text", "Контент"),
    ("orders", "control_orders", "receipt-text", "Заказы"),
    ("users", "control_users", "users", "Пользователи"),
    ("analytics", "control_analytics", "chart-no-axes-combined", "Система"),
    ("analytics", "control_web_analytics", "activity", "Веб-аналитика"),
    ("staff", "control_staff", "shield-check", "Роли"),
]


def get_staff_profile(user):
    if not user.is_authenticated:
        return None
    return getattr(user, "staff_profile", None)


def has_control_access(user):
    if not user.is_authenticated or not user.is_staff or not user.is_active:
        return False
    if user.is_superuser:
        return True
    profile = get_staff_profile(user)
    return bool(profile and profile.is_active and profile.can("dashboard"))


def user_can(user, permission):
    if not user.is_authenticated or not user.is_staff or not user.is_active:
        return False
    if user.is_superuser:
        return True
    profile = get_staff_profile(user)
    return bool(profile and profile.can(permission))


def control_nav_for(user, active_name):
    items = []
    for permission, url_name, icon, label in CONTROL_NAV:
        if user_can(user, permission):
            items.append(
                {
                    "label": label,
                    "url": reverse(url_name),
                    "icon": icon,
                    "active": active_name == url_name,
                }
            )
    return items


def role_capability_rows():
    labels = dict(StaffProfile.Role.choices)
    permissions = [
        ("products", "Товары"),
        ("content", "Контент"),
        ("orders", "Заказы"),
        ("users", "Пользователи"),
        ("analytics", "Аналитика"),
        ("staff", "Роли"),
    ]
    rows = []
    for role, label in labels.items():
        capabilities = StaffProfile.ROLE_CAPABILITIES.get(role, set())
        rows.append(
            {
                "role": role,
                "label": label,
                "permissions": [
                    {"label": permission_label, "enabled": permission in capabilities}
                    for permission, permission_label in permissions
                ],
            }
        )
    return rows
