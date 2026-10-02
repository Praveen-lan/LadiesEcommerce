"""URL configuration for sareeshop project."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from store.sitemaps import StoreSitemap

urlpatterns = [
    path("admin/password_reset/", auth_views.PasswordResetView.as_view(), name="admin_password_reset"),
    path("admin/password_reset/done/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("admin/reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("admin/reset/done/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path('admin/', admin.site.urls),
    path('sitemap.xml', sitemap, {'sitemaps': {'store': StoreSitemap}}, name='sitemap'),
    path('', include('store.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)