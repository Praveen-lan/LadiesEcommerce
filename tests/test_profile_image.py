from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from sareeshop.wsgi import application
from store.models import Customer


def test_saved_profile_image_appears_in_the_navbar(client, db, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    customer = Customer.objects.create(name="Profile Shopper", phone="9876543210")
    session = client.session
    session["customer_id"] = customer.pk
    session.save()

    image_data = BytesIO()
    Image.new("RGB", (24, 24), "purple").save(image_data, format="PNG")
    image = SimpleUploadedFile("profile.png", image_data.getvalue(), content_type="image/png")

    response = client.post(
        reverse("store:profile"),
        {
            "name": customer.name,
            "phone": customer.phone,
            "profile_image": image,
        },
        follow=True,
    )

    customer.refresh_from_db()
    assert response.status_code == 200
    assert customer.profile_image
    assert customer.profile_image.url.startswith("/media/customers/")
    assert f'src="{customer.profile_image.url}"' in response.content.decode()
    image_response = client.get(customer.profile_image.url)
    assert image_response.status_code == 200
    assert image_response["Content-Type"] == "image/png"
    assert b"".join(image_response.streaming_content).startswith(b"\x89PNG")
