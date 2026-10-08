import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sareeshop.settings")

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from waitress import serve
from whitenoise import WhiteNoise

from store.public_media import PublicMediaFiles

static_application = WhiteNoise(
    get_wsgi_application(),
    root=str(settings.STATIC_ROOT),
    prefix="/static/",
)

application = PublicMediaFiles(static_application)

serve(
    application,
    host=os.environ.get("SAREESHOP_BIND", "0.0.0.0"),
    port=int(os.environ.get("SAREESHOP_PORT", "8001")),
    threads=8,
)
