from django.db import migrations

OLD_BRAND = "Saree Elegance"
NEW_BRAND = "Swathi Designers"

TARGETS = {
    "SiteSettings": ("shop_name", "tagline"),
    "SEO": ("site_name", "default_title", "default_description", "default_keywords"),
    "AboutPage": ("title", "subtitle", "story", "mission"),
    "TermsPage": ("title", "subtitle", "content"),
}


def forwards(apps, schema_editor):
    for model_name, field_names in TARGETS.items():
        model = apps.get_model("store", model_name)
        for instance in model.objects.all():
            updates = []
            for field_name in field_names:
                value = getattr(instance, field_name)
                if isinstance(value, str) and OLD_BRAND in value:
                    setattr(instance, field_name, value.replace(OLD_BRAND, NEW_BRAND))
                    updates.append(field_name)
            if updates:
                instance.save(update_fields=updates)


def backwards(apps, schema_editor):
    for model_name, field_names in TARGETS.items():
        model = apps.get_model("store", model_name)
        for instance in model.objects.all():
            updates = []
            for field_name in field_names:
                value = getattr(instance, field_name)
                if isinstance(value, str) and NEW_BRAND in value:
                    setattr(instance, field_name, value.replace(NEW_BRAND, OLD_BRAND))
                    updates.append(field_name)
            if updates:
                instance.save(update_fields=updates)


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0016_alter_aboutpage_story_alter_seo_default_description_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]