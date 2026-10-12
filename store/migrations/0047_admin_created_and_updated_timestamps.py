import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0046_alter_termspage_updated_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="aboutpage",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name="Created",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="loginpage",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name="Created",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="seo",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name="Created",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
                verbose_name="Last Updated",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
                verbose_name="Last Updated",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="order",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
                verbose_name="Last Updated",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="saree",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
                verbose_name="Last Updated",
            ),
            preserve_default=False,
        ),
    ]
