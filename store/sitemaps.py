from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Category, Saree, SubCategory


class StoreSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return [
            "home",
            "catalog",
            "about",
            "contact",
            "terms",
            *Category.objects.all(),
            *SubCategory.objects.select_related("category").all(),
            *Saree.objects.all(),
        ]

    def location(self, item):
        if isinstance(item, str):
            return reverse(f"store:{item}")
        return item.get_absolute_url()

    def priority(self, item):
        if isinstance(item, str):
            return 1.0 if item == "home" else 0.8
        if isinstance(item, Category):
            return 0.9
        if isinstance(item, SubCategory):
            return 0.8
        return 0.7

    def lastmod(self, item):
        if isinstance(item, Saree):
            return item.created_at
        return None
