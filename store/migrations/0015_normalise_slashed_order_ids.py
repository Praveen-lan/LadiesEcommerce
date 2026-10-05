from django.db import migrations


def _yyyymmdd(order_id):
    parts = [chunk.split("-")[0] for chunk in str(order_id).split("/")]
    digits = "".join(parts)
    return digits if len(digits) == 8 and digits.isdigit() else None


def forwards(apps, schema_editor):
    Order = apps.get_model("store", "Order")
    for order in Order.objects.order_by("created_at"):
        if "/" not in order.order_id:
            continue
        candidate = _yyyymmdd(order.order_id)
        if not candidate:
            continue
        if Order.objects.filter(order_id=candidate).exclude(pk=order.pk).exists():
            continue
        order.order_id = candidate
        order.save(update_fields=["order_id"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0014_remove_seo_canonical_base_url_remove_seo_og_image_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]