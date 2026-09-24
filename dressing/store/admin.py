from django.contrib import admin
from .models import (
    Banner,
    Category,
    Customer,
    Order,
    OrderItem,
    OTPRequest,
    Saree,
    SiteSettings,
)

admin.site.site_header = "Saree Elegance Admin"
admin.site.site_title = "Saree Elegance Admin"
admin.site.index_title = "Store Management"


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "profile_image", "created_at")
    search_fields = ("name", "phone", "email")
    list_filter = ("created_at",)


@admin.register(OTPRequest)
class OTPRequestAdmin(admin.ModelAdmin):
    list_display = ("phone", "code", "is_verified", "attempts", "expires_at", "created_at")
    list_filter = ("is_verified",)
    search_fields = ("phone", "code")
    readonly_fields = ("phone", "code", "is_verified", "attempts", "expires_at", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("name", "price", "quantity", "line_total")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_id", "name", "phone", "payment_method", "payment_status", "status", "total", "created_at")
    list_filter = ("payment_method", "payment_status", "status")
    search_fields = ("order_id", "name", "phone", "email")
    readonly_fields = ("order_id", "subtotal", "delivery_charge", "gst", "total", "created_at")
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "name", "price", "quantity", "line_total")
    search_fields = ("name", "order__order_id")


class SareeInline(admin.TabularInline):
    model = Saree
    extra = 0
    fields = ("name", "price", "mrp", "is_featured")


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("shop_name", "phone", "email")

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("title", "tier", "order")
    list_filter = ("tier",)
    inlines = [SareeInline]


@admin.register(Saree)
class SareeAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "mrp", "is_featured", "created_at")
    list_filter = ("category", "is_featured")
    search_fields = ("name", "description", "fabric")


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "order")
    list_filter = ("is_active",)