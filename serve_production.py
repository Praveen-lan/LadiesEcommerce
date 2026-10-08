import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sareeshop.settings")

from django.conf import settings
from waitress import serve
from whitenoise import WhiteNoise

from sareeshop.wsgi import application as django_application

static_application = WhiteNoise(
    django_application,
    root=str(settings.STATIC_ROOT),
    prefix="/static/",
)

serve(
    static_application,
    host=os.environ.get("SAREESHOP_BIND", "0.0.0.0"),
    port=int(os.environ.get("SAREESHOP_PORT", "8001")),
    threads=8,
)
