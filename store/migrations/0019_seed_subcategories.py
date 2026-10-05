"""Give every collection the starter sub categories and file existing sarees.

Reversible: undoing this drops every sub category, which also clears
``Saree.subcategory`` because the column is ``ON DELETE SET NULL``.
"""

from django.db import migrations
from django.utils.text import slugify

from store.models import DEFAULT_SUBCATEGORIES, guess_subcategory


def seed_subcategories(apps, schema_editor):
    Category = apps.get_model("store", "Category")
    Saree = apps.get_model("store", "Saree")
    SubCategory = apps.get_model("store", "SubCategory")

    for category in Category.objects.order_by("id").iterator():
        subcategories = []
        used = set()
        for position, (title, subtitle, keywords) in enumerate(DEFAULT_SUBCATEGORIES):
            base = slugify(title) or f"sub-category-{position}"
            slug = base
            counter = 2
            while slug in used:
                slug = f"{base}-{counter}"
                counter += 1
            used.add(slug)
            subcategory = SubCategory.objects.create(
                category=category,
                title=title,
                slug=slug,
                subtitle=subtitle,
                order=position,
            )
            subcategories.append({"keywords": keywords, "subcategory": subcategory})

        for saree in Saree.objects.filter(category=category, subcategory__isnull=True).iterator():
            match = guess_subcategory(saree, subcategories)
            if match is not None:
                saree.subcategory = match["subcategory"]
                saree.save(update_fields=["subcategory"])


def unseed_subcategories(apps, schema_editor):
    SubCategory = apps.get_model("store", "SubCategory")
    SubCategory.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0018_subcategory"),
    ]

    operations = [
        migrations.RunPython(seed_subcategories, unseed_subcategories),
    ]
