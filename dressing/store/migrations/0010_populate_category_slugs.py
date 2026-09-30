from django.db import migrations
from django.utils.text import slugify


def populate_category_slugs(apps, schema_editor):
    Category = apps.get_model("store", "Category")
    used = set(Category.objects.exclude(slug="").values_list("slug", flat=True))
    for category in Category.objects.order_by("id").iterator():
        if category.slug:
            continue
        base = slugify(category.title) or f"category-{category.pk}"
        slug = base
        counter = 2
        while slug in used:
            slug = f"{base}-{counter}"
            counter += 1
        category.slug = slug
        used.add(slug)
        category.save(update_fields=["slug"])


def clear_category_slugs(apps, schema_editor):
    Category = apps.get_model("store", "Category")
    Category.objects.update(slug="")


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0009_category_slug_alter_category_tier_cartitem"),
    ]

    operations = [
        migrations.RunPython(populate_category_slugs, clear_category_slugs),
    ]
