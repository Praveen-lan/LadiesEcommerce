"""Create the five storefront collections and merge legacy collection names."""

from django.db import migrations
from django.utils.text import slugify


COLLECTIONS = (
    ("Premium Collection", "high", 0, ("Premium Collection",)),
    ("Luxury Collection", "high", 1, ("Luxury Pure Silk",)),
    ("Base Collection", "medium", 2, ("Kalankari",)),
    ("Everyday Comfort", "basic", 3, ("Everyday Comfort",)),
    ("Budget Collection", "basic", 4, ("Budget Collection",)),
)

SUBCATEGORIES = (
    ("Silk Sarees", "silk-sarees", "Pure mulberry, Kanjivaram, Banarasi and soft silk weaves with a luminous drape."),
    ("Cotton Sarees", "cotton-sarees", "Lightweight, breathable cottons and handspun khadi for everyday grace."),
    (
        "Modern & Synthetic Fabric Sarees",
        "modern-synthetic-fabric-sarees",
        "Georgette, chiffon and crepe drapes with an easy, modern fall.",
    ),
    (
        "Printed & Embroidery Sarees",
        "printed-embroidery-sarees",
        "Block prints, zari work and hand embroidery in rich, festive detail.",
    ),
    (
        "Modern Fusion Sarees",
        "modern-fusion-sarees",
        "Indo-western drapes that blend traditional motifs with a contemporary cut.",
    ),
)


def _unique_slug(Category, title):
    base = slugify(title) or "collection"
    slug = base
    suffix = 2
    while Category.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def seed_navigation_collections(apps, schema_editor):
    Category = apps.get_model("store", "Category")
    Saree = apps.get_model("store", "Saree")
    SubCategory = apps.get_model("store", "SubCategory")

    for title, tier, order, legacy_titles in COLLECTIONS:
        category = Category.objects.filter(title=title).order_by("id").first()
        if category is None:
            for legacy_title in legacy_titles:
                category = Category.objects.filter(title__iexact=legacy_title).order_by("id").first()
                if category is not None:
                    break

        if category is None:
            category = Category.objects.create(
                title=title,
                tier=tier,
                slug=_unique_slug(Category, title),
                order=order,
            )
        else:
            category.title = title
            category.tier = tier
            category.order = order
            category.save(update_fields=["title", "tier", "order"])

        target_subcategories = {}
        for position, (subcategory_title, subcategory_slug, subtitle) in enumerate(SUBCATEGORIES):
            subcategory, _ = SubCategory.objects.get_or_create(
                category_id=category.pk,
                slug=subcategory_slug,
                defaults={
                    "title": subcategory_title,
                    "subtitle": subtitle,
                    "order": position,
                },
            )
            target_subcategories[subcategory_slug] = subcategory

        for legacy_title in legacy_titles:
            sources = Category.objects.filter(title__iexact=legacy_title).exclude(pk=category.pk)
            for source in sources:
                for saree in Saree.objects.filter(category_id=source.pk).select_related("subcategory"):
                    source_subcategory = saree.subcategory
                    target_subcategory = None
                    if source_subcategory and source_subcategory.category_id == source.pk:
                        target_subcategory = target_subcategories.get(source_subcategory.slug)
                    Saree.objects.filter(pk=saree.pk).update(
                        category_id=category.pk,
                        subcategory_id=target_subcategory.pk if target_subcategory else None,
                    )
                source.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0024_alter_paymentproof_status"),
    ]

    operations = [
        migrations.RunPython(seed_navigation_collections, migrations.RunPython.noop),
    ]
