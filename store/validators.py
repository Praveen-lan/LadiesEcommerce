import os

from django.core.exceptions import ValidationError


PAYMENT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".jfif", ".png", ".webp"}


def validate_payment_image_extension(image):
    if os.path.splitext(image.name)[1].lower() not in PAYMENT_IMAGE_EXTENSIONS:
        raise ValidationError("Please upload a JPEG, PNG, or WebP image.")
