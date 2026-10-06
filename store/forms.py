import re

from django import forms
from django.conf import settings
from django.contrib.auth import forms as auth_forms
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import URLValidator
from django.template import loader

from .models import ContactMessage, Saree, SiteSettings, SubCategory
from .maps import extract_map_source

PHONE_RE = re.compile(r"[0-9]{10}")
MOBILE_RE = re.compile(r"[6-9][0-9]{9}")
PHONE_ERROR = "Please enter a valid 10-digit mobile number starting with 6-9."
WHATSAPP_RE = re.compile(r"\d{10,15}")
REQUIRED_SITE_FIELDS = ("phone", "email", "address", "map_embed_url", "whatsapp")
MAP_URL_VALIDATOR = URLValidator(
    schemes=["http", "https"],
    message="Enter a valid map embed URL starting with http:// or https://.",
)


class SubCategoryChoiceWidget(forms.Select):
    """Tags every option with the id of the category that owns it.

    ``store/admin/subcategory-filter.js`` reads ``data-category`` so the sub
    category list narrows to the collection picked above it, without a reload.
    """

    def __init__(self, attrs=None):
        super().__init__(attrs)
        self._category_by_id = None

    def category_by_id(self):
        """Map each option value to the category that owns it.

        Built on first render, not at import time: this class is created while
        Django loads the app registry, when there is no usable database yet.
        """
        if self._category_by_id is None:
            queryset = getattr(self.choices, "queryset", None)
            self._category_by_id = (
                {obj.pk: obj.category_id for obj in queryset} if queryset is not None else {}
            )
        return self._category_by_id

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        category_id = self.category_by_id().get(getattr(value, "value", value))
        if category_id:
            option["attrs"]["data-category"] = str(category_id)
        return option


class SubCategoryChoiceField(forms.ModelChoiceField):
    """Disambiguates the style titles every category is seeded with."""

    widget = SubCategoryChoiceWidget

    def label_from_instance(self, obj):
        return f"{obj.category.title} - {obj.title}"


PRODUCT_ID_MIN_LENGTH = 4
PRODUCT_ID_MAX_LENGTH = 220
PRODUCT_ID_REQUIRED = "Enter a product ID of 4 to 220 characters."
PRODUCT_ID_TOO_SHORT = "Ensure this value has at least 4 characters (it has %s)."
PRODUCT_ID_TOO_LONG = "Ensure this value has at most 220 characters (it has %s)."


class ProductIdMixin:
    """A product ID is mandatory for new products and 4 to 220 characters long.

    Sarees created before the rule existed keep working: their blank ID stays
    editable until staff enter one.
    """

    def clean_product_id(self):
        value = (self.cleaned_data.get("product_id") or "").strip()
        if not value:
            if self.instance.pk:
                return value
            raise ValidationError(PRODUCT_ID_REQUIRED, code="required")
        if len(value) < PRODUCT_ID_MIN_LENGTH:
            raise ValidationError(PRODUCT_ID_TOO_SHORT % len(value), code="min_length")
        if len(value) > PRODUCT_ID_MAX_LENGTH:
            raise ValidationError(PRODUCT_ID_TOO_LONG % len(value), code="max_length")
        return value


class SareeAdminForm(ProductIdMixin, forms.ModelForm):
    subcategory = SubCategoryChoiceField(
        queryset=SubCategory.objects.select_related("category").order_by("category__title", "order", "id"),
        required=False,
        widget=SubCategoryChoiceWidget,
        help_text="Only sub categories belonging to the selected category can be picked.",
    )

    class Meta:
        model = Saree
        fields = "__all__"


class PaymentProofForm(forms.Form):
    """Validates the payment screenshot a customer uploads after scanning the QR."""

    MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024

    screenshot = forms.ImageField(
        required=True,
        error_messages={"required": "Upload the payment screenshot."},
    )
    reference = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "UPI reference or UTR number (optional)"}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Anything we should know (optional)"}),
    )
    order_id = forms.CharField(required=False)

    def clean_screenshot(self):
        screenshot = self.cleaned_data["screenshot"]
        if screenshot.size > self.MAX_SCREENSHOT_BYTES:
            raise ValidationError("The screenshot must be smaller than 5 MB.")
        return screenshot


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ("name", "email", "phone", "subject", "message")
        error_messages = {
            "name": {"required": "Please enter username."},
            "email": {
                "required": "Please enter Email.",
                "invalid": "Please enter Email.",
            },
            "phone": {"required": "Please enter phone number."},
            "subject": {"required": "Please enter subject."},
            "message": {"required": "Please enter Message."},
        }
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "name",
                    "placeholder": "Ex: Priya Raman",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "email",
                    "placeholder": "Ex: priya.raman@example.com",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "tel",
                    "inputmode": "numeric",
                    "maxlength": "10",
                    "pattern": "[6-9][0-9]{9}",
                    "title": "Enter a 10-digit mobile number starting with 6-9.",
                    "placeholder": "Ex: 9876543210",
                }
            ),
            "subject": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ex: I want to know the delivery time for Kanjivaram silk sarees",
                }
            ),
            "message": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": "Ex: I am looking for a wedding saree that is light weight. Please share the designs and prices.",
                }
            ),
        }

    def use_required_attribute(self):
        """Never render the HTML ``required`` attribute.

        Browsers would otherwise show their own native "This field is
        required." bubble instead of the messages configured in
        ``Meta.error_messages``.
        """
        return False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].required = True

    def clean_phone(self):
        """Require a ten-digit mobile number that starts from 6 through 9."""
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not MOBILE_RE.fullmatch(phone):
            raise ValidationError(PHONE_ERROR, code="invalid")
        return phone


class SiteSettingsForm(forms.ModelForm):
    map_embed_url = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Paste a map URL or iframe embed code"}),
    )

    class Meta:
        model = SiteSettings
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in REQUIRED_SITE_FIELDS:
            self.fields[name].required = True
        self.fields["phone"].strip = False
        self.fields["whatsapp"].help_text = "Digits only, including country code (e.g. 919876543210)."

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        if not PHONE_RE.fullmatch(phone):
            raise ValidationError("Enter a valid phone number with exactly 10 digits.", code="invalid")
        return phone

    def clean_whatsapp(self):
        digits = re.sub(r"\D", "", self.cleaned_data["whatsapp"])
        if not WHATSAPP_RE.fullmatch(digits) or not 10 <= len(digits) <= 15:
            raise ValidationError(
                "Enter a valid WhatsApp number: 10-15 digits including country code, no spaces.",
                code="invalid",
            )
        return digits

    def clean_map_embed_url(self):
        value = (self.cleaned_data.get("map_embed_url") or "").strip()
        source = extract_map_source(value)
        if not source:
            raise ValidationError("Enter a map URL or iframe embed code.", code="invalid")
        try:
            MAP_URL_VALIDATOR(source)
        except ValidationError as error:
            raise ValidationError(error.messages, code="invalid") from error
        return value


class PasswordResetForm(auth_forms.PasswordResetForm):
    """Password reset form that reports delivery failures instead of hiding them.

    Django's built-in form swallows every send error, so a misconfigured mail
    server silently turned into "we emailed you" with no email and a 500 page.
    Here the failure propagates to the view, which can re-render the form with a
    readable error.
    """

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        subject = "".join(loader.render_to_string(subject_template_name, context).splitlines())
        body = loader.render_to_string(email_template_name, context)
        message = EmailMultiAlternatives(
            subject,
            body,
            from_email or settings.DEFAULT_FROM_EMAIL,
            [to_email],
        )
        if html_email_template_name is not None:
            message.attach_alternative(
                loader.render_to_string(html_email_template_name, context),
                "text/html",
            )
        message.send()
        return message

