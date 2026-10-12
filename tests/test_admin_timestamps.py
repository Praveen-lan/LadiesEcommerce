import pytest
from django.urls import reverse
from django.utils import timezone

from store.models import Customer


@pytest.mark.django_db
def test_created_date_and_time_are_editable_in_admin(client, admin_user):
    customer = Customer.objects.create(name="Timestamp Customer", phone="9876543210")
    client.force_login(admin_user)

    response = client.get(reverse("admin:store_customer_change", args=[customer.pk]))
    content = response.content.decode()

    assert response.status_code == 200
    assert content.index("<h2>Last updated</h2>") < content.index("<h2>Created at</h2>")
    assert 'name="created_date"' in content
    assert 'name="created_time"' in content
    assert 'name="last_updated_date"' in content
    assert 'name="last_updated_time"' in content
    form = response.context["adminform"].form
    assert str(form.fields["created_date"].label) == "<strong>Date</strong>"
    assert str(form.fields["created_time"].label) == "<strong>Time</strong>"
    assert str(form.fields["last_updated_date"].label) == "<strong>Date</strong>"
    assert str(form.fields["last_updated_time"].label) == "<strong>Time</strong>"
    assert form.fields["created_date"].widget.__class__.__name__ == "AdminDateWidget"
    assert form.fields["created_time"].widget.__class__.__name__ == "AdminTimeWidget"
    assert form.fields["last_updated_date"].widget.__class__.__name__ == "AdminDateWidget"
    assert form.fields["last_updated_time"].widget.__class__.__name__ == "AdminTimeWidget"

    response = client.post(
        reverse("admin:store_customer_change", args=[customer.pk]),
        {
            "name": customer.name,
            "phone": customer.phone,
            "created_date": "2025-02-01",
            "created_time": "09:25:00",
            "last_updated_date": "2026-03-05",
            "last_updated_time": "16:40:00",
            "_save": "Save",
        },
    )

    assert response.status_code == 302
    customer.refresh_from_db()
    created = timezone.localtime(customer.created_at).strftime("%Y-%m-%d %H:%M:%S")
    updated = timezone.localtime(customer.updated_at).strftime("%Y-%m-%d %H:%M:%S")
    assert created == "2025-02-01 09:25:00"
    assert updated == "2026-03-05 16:40:00"
