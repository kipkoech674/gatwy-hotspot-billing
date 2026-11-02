from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("hotspot", "0003_seed_main_location")]

    operations = [
        migrations.AddField(
            model_name="purchase",
            name="access_error",
            field=models.CharField(blank=True, max_length=160),
        ),
    ]
