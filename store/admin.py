from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.http import unquote
from django import forms

from .forms import SiteSettingsForm
from .models import (
    AboutPage,
    Banner,
    Category,
    ContactMessage,
    Customer,
    Order,
    OrderItem,
    OTPRequest,
    Saree,
    SEO,
    SiteSettings,
    TermsPage,
)


class CategoryAdminForm(forms.ModelForm):
    slug = forms.SlugField(required=False)

    class Meta:
        model = Category
        fields = "__all__"

    def clean_slug(self):
        slug = self.cleaned_data["slug"]
        base = slug
        suffix = 2
        while slug and Category.objects.filter(slug=slug).exclude(pk=self.instance.pk).exists():
            slug = f"{base}-{suffix}"
            suffix += 1
        return slug


admin.site.site_header = "Saree Elegance Admin"
admin.site.site_title = "Saree Elegance Admin"
admin.site.index_title = "Store Management"

# Static path of the helper that routes the object "Delete" button to the ticked
# inline rows. It must stay a plain static path: Django percent-encodes a "?"
# inside the path, which turns a cache-busting query string into a 404 and
# silently disables the whole selected-rows delete flow.
SELECTED_INLINE_DELETE_JS = "store/admin/selected-inline-delete.js"


@admin.register(AboutPage)
class AboutPageAdmin(admin.ModelAdmin):
    list_display = ("title", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not AboutPage.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TermsPage)
class TermsPageAdmin(admin.ModelAdmin):
    list_display = ("title", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not TermsPage.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "subject", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("name", "email", "phone", "subject", "message")
    readonly_fields = ("created_at",)
    list_editable = ("is_read",)


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
    can_delete = True
    fields = ("name", "price", "quantity", "line_total", "remove_item")
    readonly_fields = ("name", "price", "quantity", "line_total", "remove_item")

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Action")
    def remove_item(self, obj):
        if not obj.pk:
            return "-"
        url = reverse("admin:store_order_remove_item", args=[obj.order_id, obj.pk])
        return format_html('<a class="deletelink" href="{}">Remove item</a>', url)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_id", "name", "phone", "payment_method", "payment_status", "status", "total", "created_at")
    list_filter = ("payment_method", "payment_status", "status")
    search_fields = ("order_id", "name", "phone", "email")
    readonly_fields = ("order_id", "subtotal", "delivery_charge", "gst", "total", "created_at")
    inlines = [OrderItemInline]
    delete_confirmation_template = "admin/store/order/delete_confirmation.html"

    class Media:
        js = (SELECTED_INLINE_DELETE_JS,)

    def get_urls(self):
        return [
            path(
                "<int:order_id>/remove-item/<int:item_id>/",
                self.admin_site.admin_view(self.remove_item_view),
                name="store_order_remove_item",
            )
        ] + super().get_urls()

    def remove_item_view(self, request, order_id, item_id):
        order = self.get_object(request, order_id)
        if order is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, order_id)
        if not self.has_change_permission(request, order):
            raise PermissionDenied

        item = order.items.filter(pk=item_id).first()
        if item is None:
            self.message_user(request, "That item is no longer part of this order.", messages.ERROR)
            return HttpResponseRedirect(reverse("admin:store_order_change", args=[order.pk]))

        if request.method == "POST":
            if order.items.count() <= 1:
                self.message_user(
                    request,
                    "An order must keep at least one item. Cancel the order instead if it was placed by mistake.",
                    messages.ERROR,
                )
            else:
                name = item.name
                item.delete()
                order.refresh_from_db()
                order.recalculate_totals()
                self.message_user(
                    request,
                    f'Removed "{name}" from order {order.order_id}. Totals have been recalculated.',
                )
            return HttpResponseRedirect(reverse("admin:store_order_change", args=[order.pk]))

        context = {
            **self.admin_site.each_context(request),
            "title": f"Remove {item.name} from order {order.order_id}?",
            "order": order,
            "item": item,
            "opts": self.opts,
        }
        return TemplateResponse(request, "admin/store/order/remove_item.html", context)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        response = super().changeform_view(request, object_id, form_url, extra_context)
        if request.method == "POST" and object_id and response.status_code == 302:
            if any(key.endswith("-DELETE") and value for key, value in request.POST.items()):
                order = self.get_object(request, unquote(object_id))
                if order is not None:
                    order.recalculate_totals()
        return response

    def delete_view(self, request, object_id, extra_context=None):
        order = self.get_object(request, unquote(object_id))
        if order is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, object_id)
        selected_ids = request.GET.getlist("selected_items")
        if request.method == "POST":
            selected_ids = request.POST.getlist("selected_items")
        selected_ids = list(dict.fromkeys(selected_ids))
        if selected_ids:
            item_inline = next(
                inline for inline in self.get_inline_instances(request, order)
                if isinstance(inline, OrderItemInline)
            )
            if not self.has_change_permission(request, order) or not item_inline.has_delete_permission(request, order):
                raise PermissionDenied

            items = list(order.items.filter(pk__in=selected_ids))
            if len(items) != len(selected_ids):
                self.message_user(request, "One or more selected items are no longer part of this order.", messages.ERROR)
                return HttpResponseRedirect(reverse("admin:store_order_change", args=[order.pk]))

            can_delete = len(items) < order.items.count()
            if request.method == "POST" and request.POST.get("delete_selected_items") == "yes":
                if not can_delete:
                    self.message_user(
                        request,
                        "An order must keep at least one item. Cancel the order instead if it was placed by mistake.",
                        messages.ERROR,
                    )
                    return HttpResponseRedirect(reverse("admin:store_order_change", args=[order.pk]))

                names = [item.name for item in items]
                OrderItem.objects.filter(pk__in=selected_ids, order=order).delete()
                order.refresh_from_db()
                order.recalculate_totals()
                self.message_user(
                    request,
                    f'Removed {len(names)} selected item(s) from order {order.order_id}: {", ".join(names)}. Totals have been recalculated.',
                )
                return HttpResponseRedirect(reverse("admin:store_order_change", args=[order.pk]))

            context = {
                **self.admin_site.each_context(request),
                "title": f"Remove {len(items)} selected item(s) from order {order.order_id}?",
                "order": order,
                "items": items,
                "selected_ids": [item.pk for item in items],
                "can_delete": can_delete,
                "opts": self.opts,
            }
            return TemplateResponse(request, "admin/store/order/delete_selected_items.html", context)

        if request.method == "POST" and request.POST.get("confirm_order_id", "").strip() != order.order_id:
            self.message_user(
                request,
                f'Type the order ID "{order.order_id}" exactly to confirm deleting the whole order.',
                messages.ERROR,
            )
            return HttpResponseRedirect(reverse("admin:store_order_delete", args=[order.pk]))
        extra_context = extra_context or {}
        extra_context["order"] = order
        return super().delete_view(request, object_id, extra_context)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "name", "price", "quantity", "line_total")
    search_fields = ("name", "order__order_id")


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    form = SiteSettingsForm
    list_display = ("shop_name", "phone", "email")

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SEO)
class SEOAdmin(admin.ModelAdmin):
    list_display = ("site_name", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not SEO.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class SareeInlineForm(forms.ModelForm):
    class Meta:
        model = Saree
        fields = ("name", "price", "mrp", "fabric", "description", "image", "image_url", "is_featured")
        widgets = {
            "image_url": forms.URLInput(attrs={"placeholder": "https://example.com/image.jpg"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            for name, field in self.fields.items():
                field.disabled = name != "is_featured"


class SareeInline(admin.TabularInline):
    model = Saree
    form = SareeInlineForm
    extra = 0
    can_delete = True
    fields = ("name", "price", "mrp", "fabric", "description", "image", "image_url", "is_featured", "remove_saree")
    show_change_link = False

    def get_readonly_fields(self, request, obj=None):
        return ("remove_saree",)

    @admin.display(description="Action")
    def remove_saree(self, obj):
        if not obj.pk:
            return "-"
        url = reverse("admin:store_category_remove_saree", args=[obj.category_id, obj.pk])
        return format_html('<a class="deletelink" href="{}">Remove saree</a>', url)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    form = CategoryAdminForm
    list_display = ("title", "tier", "order", "saree_count")
    list_filter = ("tier",)
    search_fields = ("title", "subtitle")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [SareeInline]
    delete_confirmation_template = "admin/store/category/delete_confirmation.html"

    class Media:
        js = (SELECTED_INLINE_DELETE_JS,)

    @admin.display(description="Sarees")
    def saree_count(self, obj):
        return obj.sarees.count()

    def get_urls(self):
        return [
            path(
                "<int:category_id>/remove-saree/<int:saree_id>/",
                self.admin_site.admin_view(self.remove_saree_view),
                name="store_category_remove_saree",
            )
        ] + super().get_urls()

    def remove_saree_view(self, request, category_id, saree_id):
        category = self.get_object(request, category_id)
        if category is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, category_id)
        if not self.has_change_permission(request, category):
            raise PermissionDenied

        saree = category.sarees.filter(pk=saree_id).first()
        if saree is None:
            self.message_user(request, "That saree is no longer in this category.", messages.ERROR)
            return HttpResponseRedirect(reverse("admin:store_category_change", args=[category.pk]))

        if request.method == "POST":
            name = saree.name
            saree.delete()
            self.message_user(
                request,
                f'Removed "{name}" from category "{category.title}". The category was kept.',
            )
            return HttpResponseRedirect(reverse("admin:store_category_change", args=[category.pk]))

        context = {
            **self.admin_site.each_context(request),
            "title": f"Remove {saree.name} from {category.title}?",
            "category": category,
            "saree": saree,
            "opts": self.opts,
        }
        return TemplateResponse(request, "admin/store/category/remove_saree.html", context)

    def delete_view(self, request, object_id, extra_context=None):
        category = self.get_object(request, unquote(object_id))
        if category is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, object_id)
        selected_ids = request.GET.getlist("selected_sarees")
        if request.method == "POST":
            selected_ids = request.POST.getlist("selected_sarees")
        selected_ids = list(dict.fromkeys(selected_ids))
        if selected_ids:
            saree_admin = self.admin_site._registry[Saree]
            if not self.has_change_permission(request, category) or not saree_admin.has_delete_permission(request):
                raise PermissionDenied

            sarees = list(category.sarees.filter(pk__in=selected_ids))
            if len(sarees) != len(selected_ids):
                self.message_user(request, "One or more selected sarees are no longer in this category.", messages.ERROR)
                return HttpResponseRedirect(reverse("admin:store_category_change", args=[category.pk]))

            if request.method == "POST" and request.POST.get("delete_selected_sarees") == "yes":
                names = [saree.name for saree in sarees]
                Saree.objects.filter(pk__in=selected_ids, category=category).delete()
                self.message_user(
                    request,
                    f'Removed {len(names)} selected saree(s) from "{category.title}": {", ".join(names)}. The category was kept.',
                )
                return HttpResponseRedirect(reverse("admin:store_category_change", args=[category.pk]))

            context = {
                **self.admin_site.each_context(request),
                "title": f"Remove {len(sarees)} selected saree(s) from {category.title}?",
                "category": category,
                "sarees": sarees,
                "selected_ids": [saree.pk for saree in sarees],
                "opts": self.opts,
            }
            return TemplateResponse(request, "admin/store/category/delete_selected_sarees.html", context)

        if request.method == "POST" and request.POST.get("confirm_category_title", "").strip() != category.title:
            self.message_user(
                request,
                f'Type the category title "{category.title}" exactly to confirm deleting the whole category.',
                messages.ERROR,
            )
            return HttpResponseRedirect(reverse("admin:store_category_delete", args=[category.pk]))
        extra_context = extra_context or {}
        extra_context["category"] = category
        return super().delete_view(request, object_id, extra_context)


@admin.register(Saree)
class SareeAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "mrp", "is_featured", "created_at")
    list_filter = ("category", "is_featured")
    search_fields = ("name", "description", "fabric")


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "order")
    list_filter = ("is_active",)