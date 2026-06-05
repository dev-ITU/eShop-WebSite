from django.urls import path

from . import admin_views

urlpatterns = [
    path("", admin_views.dashboard, name="control_dashboard"),
    path("products/", admin_views.products, name="control_products"),
    path("products/new/", admin_views.product_form, name="control_product_create"),
    path("products/<int:pk>/", admin_views.product_form, name="control_product_edit"),
    path("categories/", admin_views.categories, name="control_categories"),
    path("categories/new/", admin_views.category_form, name="control_category_create"),
    path("categories/<int:pk>/", admin_views.category_form, name="control_category_edit"),
    path("content/", admin_views.content, name="control_content"),
    path("content/new/", admin_views.content_form, name="control_content_create"),
    path("content/<int:pk>/", admin_views.content_form, name="control_content_edit"),
    path("orders/", admin_views.orders, name="control_orders"),
    path("users/", admin_views.users, name="control_users"),
    path("analytics/", admin_views.analytics, name="control_analytics"),
    path("web-analytics/", admin_views.web_analytics, name="control_web_analytics"),
    path("staff/", admin_views.staff, name="control_staff"),
    path("staff/new/", admin_views.staff_create, name="control_staff_create"),
    path("staff/<int:pk>/", admin_views.staff_edit, name="control_staff_edit"),
    path("service/", admin_views.service, name="control_service"),
]
