"""URL configuration for sareeshop project."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from store.sitemaps import StoreSitemap
from store.views import (
    StorePasswordResetCompleteView,
    StorePasswordResetConfirmView,
    StorePasswordResetDoneView,
    StorePasswordResetView,
)

urlpatterns = [
    path("admin/password_reset/", StorePasswordResetView.as_view(), name="admin_password_reset"),
    path("admin/password_reset/done/", StorePasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "admin/reset/<uidb64>/<token>/",
        StorePasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "admin/reset/done/",
        StorePasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path('admin/', admin.site.urls),
    path('sitemap.xml', sitemap, {'sitemaps': {'store': StoreSitemap}}, name='sitemap'),
    path('', include('store.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
