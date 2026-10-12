import pytest
from django.test import override_settings


@pytest.mark.django_db
@pytest.mark.parametrize("debug", [True, False])
def test_unknown_url_renders_animated_branded_404(client, debug):
    with override_settings(DEBUG=debug):
        response = client.get("/this-page-does-not-exist/")

    assert response.status_code == 404
    assert b"This page wandered off" in response.content
    assert b'class="not-found-art"' in response.content
    assert b"Back to the collection" in response.content
    assert b"/static/css/style.css" in response.content
