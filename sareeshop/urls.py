"""URL configuration for sareeshop project."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from store.sitemaps import StoreSitemap
from store.views import (
    admin_password_reset_change,
    admin_password_reset_complete,
    admin_password_reset_request,
    admin_password_reset_verify,
)

urlpatterns = [
    path("admin/password_reset/", admin_password_reset_request, name="admin_password_reset"),
    path("admin/password_reset/verify/", admin_password_reset_verify, name="admin_password_reset_verify"),
    path("admin/password_reset/change/", admin_password_reset_change, name="admin_password_reset_change"),
    path("admin/password_reset/complete/", admin_password_reset_complete, name="password_reset_complete"),
    path('admin/', admin.site.urls),
    path('sitemap.xml', sitemap, {'sitemaps': {'store': StoreSitemap}}, name='sitemap'),
    path('', include('store.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
