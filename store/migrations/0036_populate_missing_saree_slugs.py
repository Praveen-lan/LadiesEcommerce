from django.db import migrations
from django.utils.text import slugify


def populate_missing_saree_slugs(apps, schema_editor):
    Saree = apps.get_model("store", "Saree")
    database = schema_editor.connection.alias
    existing_slugs = set(
        Saree.objects.using(database).exclude(slug="").values_list("slug", flat=True)
    )

    for saree in Saree.objects.using(database).filter(slug="").order_by("pk").iterator():
        base = slugify(saree.name) or "saree"
        slug = base
        counter = 2
        while slug in existing_slugs:
            slug = f"{base}-{counter}"
            counter += 1

        Saree.objects.using(database).filter(pk=saree.pk).update(slug=slug)
        existing_slugs.add(slug)


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0035_customer_shopping_cart"),
    ]

    operations = [
        migrations.RunPython(populate_missing_saree_slugs, migrations.RunPython.noop),
    ]
