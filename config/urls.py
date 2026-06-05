from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from shop.auth_views import UnifiedLoginView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("control/", include("shop.admin_urls")),
    path("login/", UnifiedLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("shop.urls")),
]
