import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0043_remove_paymentproof_reviewed_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="termspage",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name="Created at",
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="termspage",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="Last updated"),
        ),
    ]
