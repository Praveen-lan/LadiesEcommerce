from django import forms

from .models import ContactMessage


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
