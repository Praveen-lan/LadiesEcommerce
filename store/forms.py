import re

from django import forms
from django.conf import settings
from django.contrib.auth import forms as auth_forms
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import URLValidator
from django.template import loader

from .models import ContactMessage, SiteSettings

PHONE_RE = re.compile(r"[0-9]{10}")
WHATSAPP_RE = re.compile(r"\d{10,15}")
REQUIRED_SITE_FIELDS = ("phone", "email", "address", "map_embed_url", "whatsapp")
MAP_URL_VALIDATOR = URLValidator(
    schemes=["http", "https"],
    message="Enter a valid map embed URL starting with http:// or https://.",
)


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ("name", "email", "phone", "subject", "message")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "autocomplete": "tel"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "How can we help?"}),
            "message": forms.Textarea(attrs={"class": "form-control", "rows": 6, "placeholder": "Write your enquiry here..."}),
        }


class SiteSettingsForm(forms.ModelForm):
    map_embed_url = forms.CharField(
        widget=forms.URLInput,
        validators=[MAP_URL_VALIDATOR],
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


