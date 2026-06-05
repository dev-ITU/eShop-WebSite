from django.contrib import admin

from .models import Category, Order, OrderItem, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ("sort_order", "is_active")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "category", "price", "stock", "is_featured", "is_active")
    list_filter = ("category", "brand", "color", "memory", "is_featured", "is_active")
    search_fields = ("name", "brand", "description")
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ("stock", "is_featured", "is_active")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_name", "price", "quantity")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "user", "status", "payment_status", "total", "created_at")
    list_filter = ("status", "payment_status", "created_at")
    search_fields = ("order_number", "customer_name", "email", "phone")
    readonly_fields = ("order_number", "pickup_code", "qr_svg", "created_at", "paid_at", "ready_at")
    inlines = [OrderItemInline]
