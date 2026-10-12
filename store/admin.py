import mimetypes
from datetime import datetime

from django.contrib import admin, messages
from django.core.exceptions import FieldDoesNotExist, PermissionDenied
from django.db import models
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.formats import date_format, time_format
from django.utils.html import format_html
from django.utils.http import unquote
from django import forms
from django.contrib.admin.widgets import AdminDateWidget, AdminTimeWidget
from django_prose_editor.fields import ProseEditorFormField
from django_prose_editor.widgets import AdminProseEditorWidget

from .forms import OptionalSareeAdminFieldsMixin, ProductIdMixin, SareeAdminForm, SiteSettingsForm
from .richtext import sanitize_terms_html
from .validators import ADMIN_IMAGE_UPLOAD_ERROR, validate_admin_image_extension, validate_image_extension
from .models import (
    AboutPage,
    Banner,
    Category,
    ContactMessage,
    Customer,
    Order,
    OrderItem,
    LoginPage,
    PaymentProof,
    PaymentQR,
    Saree,
    SEO,
    SiteSettings,
    SubCategory,
    SLUG_VALIDATION_MESSAGE,
    TermsPage,
)


class CategoryAdminForm(forms.ModelForm):
    slug = forms.CharField(
        label="Slug",
        required=False,
        max_length=150,
        error_messages={"required": "Please enter a slug."},
        help_text=SLUG_VALIDATION_MESSAGE,
        widget=forms.TextInput(
            attrs={
                "pattern": "[A-Za-z0-9]+",
                "title": SLUG_VALIDATION_MESSAGE,
            }
        ),
    )
    tier = forms.ChoiceField(
        choices=Category.Tier.choices,
        required=False,
        widget=forms.HiddenInput,
    )

    class Meta:
        model = Category
        fields = "__all__"

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "")
        if self.instance.pk and slug == self.instance.slug:
            return slug
        if not slug:
            if self.instance.pk:
                return slug
            raise forms.ValidationError("Please enter a slug.", code="required")
        if not slug.isascii() or not slug.isalnum():
            raise forms.ValidationError(
                SLUG_VALIDATION_MESSAGE,
                code="invalid",
            )
        return slug

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = not bool(self.instance.pk)
        self.fields["tier"].initial = self.instance.tier if self.instance.pk else Category.Tier.BASIC

    def clean_tier(self):
        return self.instance.tier if self.instance.pk else Category.Tier.BASIC


class SubCategoryAdminForm(forms.ModelForm):
    """Validate new subcategory slugs while preserving existing legacy slugs."""

    slug = forms.CharField(
        label="Slug",
        required=False,
        max_length=150,
        error_messages={"required": "Please enter a slug."},
        help_text=SLUG_VALIDATION_MESSAGE,
        widget=forms.TextInput(
            attrs={
                "pattern": "[A-Za-z0-9]+",
                "title": SLUG_VALIDATION_MESSAGE,
            }
        ),
    )

    class Meta:
        model = SubCategory
        fields = "__all__"

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "")
        if self.instance.pk and slug == self.instance.slug:
            return slug
        if not slug:
            if self.instance.pk:
                return slug
            raise forms.ValidationError("Please enter a slug.", code="required")
        if not slug.isascii() or not slug.isalnum():
            raise forms.ValidationError(
                SLUG_VALIDATION_MESSAGE,
                code="invalid",
            )
        return slug

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = not bool(self.instance.pk)


admin.site.site_header = "Swathi Designers Admin"
admin.site.site_title = "Swathi Designers Admin"
admin.site.index_title = "Store Management"


def blank_text_initial(form):
    """Clear the pre-filled text on an unsaved form so "+ Add" opens empty.

    Django fills a new form with each field's model default, which for this
    project is long boilerplate copy - the About Page story, the whole Terms
    text, the default SEO title and keywords. Staff adding a new record want
    empty boxes, so those are dropped here. Only free-text boxes are cleared:
    numbers, checkboxes and choice dropdowns keep their defaults because they
    are required fields and blanking them would block saving. Model defaults
    stay untouched for the code paths that build unsaved instances directly.
    """
    for field in form.fields.values():
        field.label = format_html("<strong>{}</strong>", field.label)
        if isinstance(field, forms.ImageField):
            field.validators = [
                validator
                for validator in field.validators
                if validator is not validate_image_extension
            ]
            if validate_admin_image_extension not in field.validators:
                field.validators.append(validate_admin_image_extension)
            field.error_messages["invalid_image"] = ADMIN_IMAGE_UPLOAD_ERROR
            field.help_text = ADMIN_IMAGE_UPLOAD_ERROR

    if form.instance.pk is not None:
        return
    for name, field in form.fields.items():
        try:
            model_field = form._meta.model._meta.get_field(name)
        except FieldDoesNotExist:
            continue
        if not isinstance(
            field.widget,
            (forms.CheckboxInput, forms.RadioSelect, forms.Select, forms.HiddenInput),
        ):
            if isinstance(model_field, (models.CharField, models.TextField)):
                field.initial = ""
                field.widget.attrs.setdefault("placeholder", "")


class BlankTextOnAddMixin:
    """Applies :func:`blank_text_initial` to a ModelAdmin's add form."""

    def get_form(self, request, obj=None, **kwargs):
        form_class = super().get_form(request, obj, **kwargs)

        class BlankOnAddForm(form_class):
            def __init__(self, *args, **inner_kwargs):
                super().__init__(*args, **inner_kwargs)
                blank_text_initial(self)

        BlankOnAddForm.__name__ = form_class.__name__
        return BlankOnAddForm


def last_updated_date_field():
    return forms.DateField(label="Date", required=False, widget=AdminDateWidget)


def last_updated_time_field():
    return forms.TimeField(label="Time", required=False, widget=AdminTimeWidget)


def created_date_field():
    return forms.DateField(label="Date", required=False, widget=AdminDateWidget)


def created_time_field():
    return forms.TimeField(label="Time", required=False, widget=AdminTimeWidget)


class TimestampFieldsMixin:
    timestamp_model_fields = {
        "created": "created_at",
        "last_updated": "updated_at",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for prefix, model_field in self.timestamp_model_fields.items():
            timestamp = getattr(self.instance, model_field) if self.instance.pk else None
            timestamp = timestamp or timezone.now()
            local_timestamp = timezone.localtime(timestamp)
            self.initial.setdefault(f"{prefix}_date", local_timestamp.date())
            self.initial.setdefault(f"{prefix}_time", local_timestamp.time())

    def clean(self):
        cleaned_data = super().clean()
        for prefix in self.timestamp_model_fields:
            date_field = f"{prefix}_date"
            time_field = f"{prefix}_time"
            has_date = cleaned_data.get(date_field) is not None
            has_time = cleaned_data.get(time_field) is not None
            if has_date != has_time:
                self.add_error(date_field, "Enter both a date and a time.")
                self.add_error(time_field, "Enter both a date and a time.")
        return cleaned_data


class LastUpdatedAdminForm(TimestampFieldsMixin, forms.ModelForm):
    created_date = created_date_field()
    created_time = created_time_field()
    last_updated_date = last_updated_date_field()
    last_updated_time = last_updated_time_field()

    class Meta:
        model = LoginPage
        fields = "__all__"


class AboutPageAdminForm(TimestampFieldsMixin, forms.ModelForm):
    created_date = created_date_field()
    created_time = created_time_field()
    last_updated_date = last_updated_date_field()
    last_updated_time = last_updated_time_field()

    class Meta:
        model = AboutPage
        fields = "__all__"


class PaymentQRAdminForm(TimestampFieldsMixin, forms.ModelForm):
    created_date = created_date_field()
    created_time = created_time_field()
    last_updated_date = last_updated_date_field()
    last_updated_time = last_updated_time_field()

    class Meta:
        model = PaymentQR
        fields = "__all__"


class PaymentProofAdminForm(TimestampFieldsMixin, forms.ModelForm):
    created_date = created_date_field()
    created_time = created_time_field()
    last_updated_date = last_updated_date_field()
    last_updated_time = last_updated_time_field()
    timestamp_model_fields = {
        "created": "submitted_at",
        "last_updated": "updated_at",
    }

    class Meta:
        model = PaymentProof
        fields = "__all__"


# Static path of the helper that routes the object "Delete" button to the ticked
# inline rows. It must stay a plain static path: Django percent-encodes a "?"
# inside the path, which turns a cache-busting query string into a 404 and
# silently disables the whole selected-rows delete flow.
SELECTED_INLINE_DELETE_JS = "store/admin/selected-inline-delete.js"
SUBCATEGORY_FILTER_JS = "store/admin/subcategory-filter.js"


class TimestampAdminMixin:
    timestamp_model_fields = {
        "created": "created_at",
        "last_updated": "updated_at",
    }

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if len(fieldsets) != 1 or fieldsets[0][0] is not None:
            return fieldsets

        fields = tuple(fieldsets[0][1]["fields"])
        timestamp_fields = {
            f"{prefix}_{part}"
            for prefix in self.timestamp_model_fields
            for part in ("date", "time")
        }
        remaining_fields = tuple(field for field in fields if field not in timestamp_fields)
        grouped_fieldsets = []
        if remaining_fields:
            grouped_fieldsets.append((None, {"fields": remaining_fields}))
        for prefix, heading in (("last_updated", "Last updated"), ("created", "Created at")):
            group = tuple(
                field
                for field in (f"{prefix}_date", f"{prefix}_time")
                if field in fields
            )
            if group:
                grouped_fieldsets.append((heading, {"fields": group}))
        return grouped_fieldsets

    @admin.display(description="Created Date", empty_value="—")
    def created_date(self, obj):
        timestamp_field = self.timestamp_model_fields.get("created")
        timestamp = getattr(obj, timestamp_field, None) if timestamp_field else None
        if timestamp is None:
            return None
        return date_format(timezone.localtime(timestamp), "DATE_FORMAT")

    @admin.display(description="Created Time", empty_value="—")
    def created_time(self, obj):
        timestamp_field = self.timestamp_model_fields.get("created")
        timestamp = getattr(obj, timestamp_field, None) if timestamp_field else None
        if timestamp is None:
            return None
        return time_format(timezone.localtime(timestamp).time(), "TIME_FORMAT")

    @admin.display(description="Last Updated Date", empty_value="—")
    def last_updated_date(self, obj):
        timestamp_field = self.timestamp_model_fields.get("last_updated")
        timestamp = getattr(obj, timestamp_field, None) if timestamp_field else None
        if timestamp is None:
            return None
        return date_format(timezone.localtime(timestamp), "DATE_FORMAT")

    @admin.display(description="Last Updated Time", empty_value="—")
    def last_updated_time(self, obj):
        timestamp_field = self.timestamp_model_fields.get("last_updated")
        timestamp = getattr(obj, timestamp_field, None) if timestamp_field else None
        if timestamp is None:
            return None
        return time_format(timezone.localtime(timestamp).time(), "TIME_FORMAT")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        updates = {}
        for prefix, model_field in self.timestamp_model_fields.items():
            date_value = form.cleaned_data.get(f"{prefix}_date")
            time_value = form.cleaned_data.get(f"{prefix}_time")
            if date_value is None or time_value is None:
                continue
            local_timestamp = datetime.combine(date_value, time_value)
            updates[model_field] = timezone.make_aware(
                local_timestamp,
                timezone.get_current_timezone(),
            )
        if updates:
            self.model._default_manager.filter(pk=obj.pk).update(**updates)
            for model_field, timestamp in updates.items():
                setattr(obj, model_field, timestamp)


@admin.register(LoginPage)
class LoginPageAdmin(TimestampAdminMixin, BlankTextOnAddMixin, admin.ModelAdmin):
    timestamp_model_fields = {
        "created": "created_at",
        "last_updated": "updated_at",
    }
    form = LastUpdatedAdminForm
    fields = (
        "heading",
        "description",
        "tagline",
        "background_image",
        "created_date",
        "created_time",
        "last_updated_date",
        "last_updated_time",
    )
    list_display = (
        "heading",
        "created_date",
        "created_time",
        "last_updated_date",
        "last_updated_time",
    )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AboutPage)
class AboutPageAdmin(TimestampAdminMixin, BlankTextOnAddMixin, admin.ModelAdmin):
    timestamp_model_fields = {
        "created": "created_at",
        "last_updated": "updated_at",
    }
    form = AboutPageAdminForm
    list_display = (
        "title",
        "created_date",
        "created_time",
        "last_updated_date",
        "last_updated_time",
    )

    def has_delete_permission(self, request, obj=None):
        return False


class TermsPageAdminForm(TimestampFieldsMixin, forms.ModelForm):
    created_date = created_date_field()
    created_time = created_time_field()
    last_updated_date = last_updated_date_field()
    last_updated_time = last_updated_time_field()
    content = ProseEditorFormField(
        config={
            "extensions": {
                "Bold": True,
                "Blockquote": True,
                "BulletList": True,
                "HardBreak": True,
                "Heading": {"levels": [2, 3, 4]},
                "HorizontalRule": True,
                "Italic": True,
                "ListItem": True,
                "OrderedList": True,
                "Strike": True,
                "Subscript": True,
                "Superscript": True,
                "TextAlign": True,
                "TextStyle": True,
                "Underline": True,
            },
        },
        preset="configurable",
        widget=AdminProseEditorWidget(),
    )

    class Meta:
        model = TermsPage
        fields = "__all__"

    def clean_content(self):
        return sanitize_terms_html(self.cleaned_data["content"])


@admin.register(TermsPage)
class TermsPageAdmin(TimestampAdminMixin, BlankTextOnAddMixin, admin.ModelAdmin):
    timestamp_model_fields = {
        "created": "created_at",
        "last_updated": "updated_at",
    }
    form = TermsPageAdminForm
    list_display = ("title", "created_date", "created_time", "last_updated_date", "last_updated_time")
    actions = None

    def get_fields(self, request, obj=None):
        fields = ("title", "subtitle", "content")
        return fields + (
            "created_date",
            "created_time",
            "last_updated_date",
            "last_updated_time",
        )


class ContactMessageAdminForm(TimestampFieldsMixin, forms.ModelForm):
    created_date = created_date_field()
    created_time = created_time_field()
    last_updated_date = last_updated_date_field()
    last_updated_time = last_updated_time_field()

    class Meta:
        model = ContactMessage
        fields = "__all__"


class CustomerAdminForm(TimestampFieldsMixin, forms.ModelForm):
    created_date = created_date_field()
    created_time = created_time_field()
    last_updated_date = last_updated_date_field()
    last_updated_time = last_updated_time_field()

    class Meta:
        model = Customer
        fields = "__all__"


class OrderAdminForm(TimestampFieldsMixin, forms.ModelForm):
    created_date = created_date_field()
    created_time = created_time_field()
    last_updated_date = last_updated_date_field()
    last_updated_time = last_updated_time_field()

    class Meta:
        model = Order
        fields = "__all__"


class SareeTimestampAdminForm(TimestampFieldsMixin, SareeAdminForm):
    created_date = created_date_field()
    created_time = created_time_field()
    last_updated_date = last_updated_date_field()
    last_updated_time = last_updated_time_field()


@admin.register(ContactMessage)
class ContactMessageAdmin(TimestampAdminMixin, BlankTextOnAddMixin, admin.ModelAdmin):
    timestamp_model_fields = {"created": "created_at", "last_updated": "updated_at"}
    form = ContactMessageAdminForm
    list_display = (
        "name",
        "email",
        "subject",
        "is_read",
        "created_date",
        "created_time",
        "last_updated_date",
        "last_updated_time",
    )
    list_filter = ("is_read", "created_at")
    search_fields = ("name", "email", "phone", "subject", "message")
    list_editable = ("is_read",)


@admin.register(Customer)
class CustomerAdmin(TimestampAdminMixin, BlankTextOnAddMixin, admin.ModelAdmin):
    timestamp_model_fields = {"created": "created_at", "last_updated": "updated_at"}
    form = CustomerAdminForm
    list_display = (
        "name",
        "phone",
        "profile_image",
        "created_date",
        "created_time",
        "last_updated_date",
        "last_updated_time",
    )
    search_fields = ("name", "phone")
    list_filter = ("created_at",)


class OrderItemInline(BlankTextOnAddMixin, admin.TabularInline):
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
class OrderAdmin(TimestampAdminMixin, BlankTextOnAddMixin, admin.ModelAdmin):
    timestamp_model_fields = {"created": "created_at", "last_updated": "updated_at"}
    form = OrderAdminForm
    list_display = (
        "order_id",
        "name",
        "phone",
        "payment_method",
        "payment_status",
        "status",
        "total",
        "created_date",
        "created_time",
        "last_updated_date",
        "last_updated_time",
    )
    list_filter = ("payment_method", "payment_status", "status")
    search_fields = ("order_id", "name", "phone", "email")
    readonly_fields = ("order_id", "subtotal", "delivery_charge", "gst", "total")
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
class OrderItemAdmin(BlankTextOnAddMixin, admin.ModelAdmin):
    list_display = ("order", "name", "price", "quantity", "line_total")
    search_fields = ("name", "order__order_id")


@admin.register(SiteSettings)
class SiteSettingsAdmin(BlankTextOnAddMixin, admin.ModelAdmin):
    form = SiteSettingsForm
    list_display = ("shop_name", "phone", "email")

    def has_delete_permission(self, request, obj=None):
        return False


class SEOAdminForm(TimestampFieldsMixin, forms.ModelForm):
    created_date = created_date_field()
    created_time = created_time_field()
    last_updated_date = last_updated_date_field()
    last_updated_time = last_updated_time_field()

    """Field list for SEO Settings; :class:`BlankTextOnAddMixin` blanks it."""

    class Meta:
        model = SEO
        fields = "__all__"
        exclude = ("robots_extra",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True


@admin.register(SEO)
class SEOAdmin(TimestampAdminMixin, BlankTextOnAddMixin, admin.ModelAdmin):
    """One row per SEO setup; the newest added row is the one the site uses.

    ``robots_extra`` is kept in the database (robots.txt still reads it) but is
    hidden from the form so the page only shows the meta tag settings.
    """

    form = SEOAdminForm
    timestamp_model_fields = {
        "created": "created_at",
        "last_updated": "updated_at",
    }
    fields = (
        "page_name",
        "site_name",
        "default_title",
        "default_page_description",
        "meta_title",
        "default_description",
        "default_keywords",
        "google_site_verification",
        "created_date",
        "created_time",
        "last_updated_date",
        "last_updated_time",
    )
    list_display = (
        "page_name",
        "site_name",
        "created_date",
        "created_time",
        "last_updated_date",
        "last_updated_time",
    )
    search_fields = ("page_name", "site_name")

    def has_delete_permission(self, request, obj=None):
        return False


class SareeInlineForm(OptionalSareeAdminFieldsMixin, ProductIdMixin, forms.ModelForm):
    class Meta:
        model = Saree
        fields = (
            "name",
            "product_id",
            "price",
            "mrp",
            "discount_percent",
            "delivery_charge",
            "gst_percent",
            "fabric",
            "length",
            "in_stock",
            "dispatch_note",
            "description",
            "image",
            "image_url",
            "is_featured",
        )
        widgets = {
            "image_url": forms.URLInput(attrs={"placeholder": "https://example.com/image.jpg"}),
            "product_id": forms.TextInput(
                attrs={"placeholder": "e.g. SD-SRK-1001", "minlength": 4, "maxlength": 220}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            for name, field in self.fields.items():
                field.disabled = name != "is_featured"


class SubCategoryInline(BlankTextOnAddMixin, admin.TabularInline):
    """Sub categories are created straight from the category they belong to."""

    model = SubCategory
    form = SubCategoryAdminForm
    extra = 0
    can_delete = True
    fields = ("title", "slug", "subtitle", "image", "order", "saree_count")
    readonly_fields = ("saree_count",)
    ordering = ("order", "id")

    @admin.display(description="Sarees")
    def saree_count(self, obj):
        return obj.sarees.count() if obj.pk else "-"


class SareeInline(BlankTextOnAddMixin, admin.TabularInline):
    model = Saree
    form = SareeInlineForm
    extra = 0
    can_delete = True
    fields = (
            "name",
            "product_id",
            "price",
            "mrp",
            "discount_percent",
            "delivery_charge",
            "gst_percent",
            "fabric",
            "length",
            "in_stock",
            "dispatch_note",
            "description",
            "image",
            "image_url",
            "is_featured",
            "remove_saree",
        )
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
class CategoryAdmin(BlankTextOnAddMixin, admin.ModelAdmin):
    form = CategoryAdminForm
    list_display = ("title", "saree_count", "subcategory_count")
    list_filter = ()
    search_fields = ("title", "subtitle")
    inlines = []
    delete_confirmation_template = "admin/store/category/delete_confirmation.html"

    def get_inline_instances(self, request, obj=None):
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    @admin.display(description="Sarees")
    def saree_count(self, obj):
        return obj.sarees.count()

    @admin.display(description="Sub categories")
    def subcategory_count(self, obj):
        return obj.subcategories.count()

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


class SubCategorySareeInline(BlankTextOnAddMixin, admin.TabularInline):
    """Lets staff file existing sarees into a sub category from its own page."""

    model = Saree
    form = SareeInlineForm
    fk_name = "subcategory"
    extra = 0
    can_delete = True
    fields = (
        "name",
        "product_id",
        "price",
        "mrp",
        "discount_percent",
        "delivery_charge",
        "gst_percent",
        "fabric",
        "length",
        "in_stock",
        "dispatch_note",
        "image",
        "image_url",
        "is_featured",
    )


@admin.register(SubCategory)
class SubCategoryAdmin(BlankTextOnAddMixin, admin.ModelAdmin):
    form = SubCategoryAdminForm
    list_display = ("title", "category", "saree_count")
    list_filter = ("category",)
    search_fields = ("title", "subtitle", "category__title")
    autocomplete_fields = ("category",)
    inlines = []

    @admin.display(description="Sarees")
    def saree_count(self, obj):
        return obj.sarees.count()


@admin.register(Saree)
class SareeAdmin(TimestampAdminMixin, BlankTextOnAddMixin, admin.ModelAdmin):
    timestamp_model_fields = {"created": "created_at", "last_updated": "updated_at"}
    form = SareeTimestampAdminForm
    list_display = (
        "name",
        "product_id",
        "category",
        "subcategory",
        "final_amount",
        "original_amount",
        "in_stock",
        "created_date",
        "created_time",
        "last_updated_date",
        "last_updated_time",
    )
    list_filter = ("category", "subcategory", "is_featured", "in_stock")
    search_fields = ("name", "product_id", "description", "fabric")

    @admin.display(description="Final amount", ordering="price")
    def final_amount(self, obj):
        return f"Rs {obj.final_amount}"

    @admin.display(description="Original amount", ordering="mrp")
    def original_amount(self, obj):
        return f"Rs {obj.original_amount}"

    class Media:
        js = (SUBCATEGORY_FILTER_JS,)


@admin.register(PaymentQR)
class PaymentQRAdmin(TimestampAdminMixin, BlankTextOnAddMixin, admin.ModelAdmin):
    """Lets staff upload the payment QR code shown in the payment method section."""

    timestamp_model_fields = {
        "created": "created_at",
        "last_updated": "updated_at",
    }
    form = PaymentQRAdminForm
    list_display = (
        "qr_thumbnail",
        "label",
        "upi_id",
        "is_active",
        "created_date",
        "created_time",
        "last_updated_date",
        "last_updated_time",
    )
    list_editable = ("is_active",)
    fields = (
        "image",
        "label",
        "upi_id",
        "is_active",
        "created_date",
        "created_time",
        "last_updated_date",
        "last_updated_time",
    )

    @admin.display(description="QR")
    def qr_thumbnail(self, obj):
        if not obj.image:
            return "No image"
        return format_html('<img src="{}" style="height:60px;border:1px solid #e4dec6;border-radius:6px;">', obj.image.url)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentProof)
class PaymentProofAdmin(TimestampAdminMixin, BlankTextOnAddMixin, admin.ModelAdmin):
    """Every uploaded payment screenshot, with who paid, what for and when."""

    timestamp_model_fields = {
        "created": "submitted_at",
        "last_updated": "updated_at",
    }
    form = PaymentProofAdminForm
    list_display = (
        "created_date",
        "created_time",
        "last_updated_date",
        "last_updated_time",
        "customer_name",
        "phone",
        "order_reference",
        "order_summary",
        "amount",
        "payment_method",
        "payment_state",
        "screenshot_link",
    )
    list_filter = ("status", "payment_method")
    search_fields = ("customer_name", "phone", "reference", "order__order_id", "order__name")
    ordering = ("-updated_at", "-id")
    readonly_fields = ("order_details", "order_summary", "screenshot_link")
    fields = (
        "customer_name",
        "phone",
        "order",
        "order_details",
        "amount",
        "payment_method",
        "reference",
        "screenshot",
        "screenshot_link",
        "notes",
        "status",
        "created_date",
        "created_time",
        "last_updated_date",
        "last_updated_time",
    )
    actions = ("mark_verified", "mark_rejected", "mark_pending")

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/screenshot/",
                self.admin_site.admin_view(self.payment_screenshot_view),
                name="store_paymentproof_screenshot",
            ),
        ]
        return custom_urls + super().get_urls()

    def payment_screenshot_view(self, request, object_id):
        proof = self.get_object(request, object_id)
        if proof is None:
            raise Http404
        if not self.has_view_or_change_permission(request, proof):
            raise PermissionDenied
        if not proof.screenshot:
            raise Http404
        response = FileResponse(
            proof.screenshot.open("rb"),
            content_type=mimetypes.guess_type(proof.screenshot.name)[0] or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @admin.display(description="Order details")
    def order_summary(self, obj):
        text = obj.order_details
        return text if len(text) <= 60 else text[:57] + "..."

    @admin.display(description="Payment status", ordering="status")
    def payment_state(self, obj):
        """A paid order reads "Payment done"; the screenshot still stays listed."""
        if obj.order_id and obj.order.payment_status == Order.Status.PAID:
            return "Payment done"
        return obj.get_status_display()

    @admin.display(description="Screenshot")
    def screenshot_link(self, obj):
        if not obj.screenshot:
            return "No file"
        screenshot_url = reverse("admin:store_paymentproof_screenshot", args=[obj.pk])
        return format_html(
            '<a href="{}" target="_blank" rel="noopener"><img src="{}" style="height:46px;border:1px solid #e4dec6;border-radius:6px;"></a>',
            screenshot_url,
            screenshot_url,
        )

    @admin.action(description="Mark selected as verified")
    def mark_verified(self, request, queryset):
        self._set_status(request, queryset, PaymentProof.Status.VERIFIED)

    @admin.action(description="Mark selected as rejected")
    def mark_rejected(self, request, queryset):
        self._set_status(request, queryset, PaymentProof.Status.REJECTED)

    @admin.action(description="Mark selected as pending")
    def mark_pending(self, request, queryset):
        self._set_status(request, queryset, PaymentProof.Status.PENDING)

    def _set_status(self, request, queryset, status):
        changed = 0
        for proof in queryset:
            proof.status = status
            proof.save(update_fields=["status", "updated_at"])
            changed += 1
        self.message_user(request, f"{changed} payment verification(s) updated.")


@admin.register(Banner)
class BannerAdmin(BlankTextOnAddMixin, admin.ModelAdmin):
    fields = ("title", "subtitle", "image", "is_active")
    list_display = ("title", "is_active")
    list_filter = ("is_active",)