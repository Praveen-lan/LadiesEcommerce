import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from store.validators import ADMIN_IMAGE_UPLOAD_ERROR, validate_admin_image_extension


@pytest.mark.parametrize("filename", ["image.jpg", "image.jpeg", "image.PNG"])
def test_admin_image_validator_accepts_jpg_jpeg_and_png(filename):
    validate_admin_image_extension(SimpleUploadedFile(filename, b"image"))


@pytest.mark.parametrize("filename", ["image.webp", "image.gif", "image.svg"])
def test_admin_image_validator_rejects_other_extensions(filename):
    with pytest.raises(ValidationError, match=ADMIN_IMAGE_UPLOAD_ERROR):
        validate_admin_image_extension(SimpleUploadedFile(filename, b"image"))
