import os

from django.core.exceptions import ValidationError


PAYMENT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".jfif", ".png", ".webp"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".jfif", ".png", ".webp"}
IMAGE_UPLOAD_ERROR = "Please upload an image in JPG, JPEG, PNG, or WebP format."


def validate_image_extension(image):
    if os.path.splitext(image.name)[1].lower() not in IMAGE_EXTENSIONS:
        raise ValidationError(IMAGE_UPLOAD_ERROR)


def validate_payment_image_extension(image):
    if os.path.splitext(image.name)[1].lower() not in PAYMENT_IMAGE_EXTENSIONS:
        raise ValidationError("Please upload a JPEG, PNG, or WebP image.")
