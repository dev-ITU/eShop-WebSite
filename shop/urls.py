from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.catalog, name="catalog"),
    path("products/<slug:slug>/", views.product_detail, name="product_detail"),
    path("cart/", views.cart_page, name="cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("orders/<str:order_number>/payment/", views.order_payment, name="order_payment"),
    path("orders/<str:order_number>/", views.order_detail, name="order_detail"),
    path("account/", views.account, name="account"),
    path("register/", views.register, name="register"),
    path("password-reset/", views.password_reset, name="password_reset"),
    path("api/products/", views.api_products, name="api_products"),
    path("api/catalog-meta/", views.api_catalog_meta, name="api_catalog_meta"),
    path("api/cart/", views.api_cart, name="api_cart"),
    path("api/account/", views.api_account, name="api_account"),
]
