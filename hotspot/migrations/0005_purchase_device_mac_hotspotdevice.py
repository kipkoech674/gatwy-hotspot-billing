from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("hotspot", "0004_purchase_access_error")]

    operations = [
        migrations.AddField(
            model_name="purchase",
            name="device_mac",
            field=models.CharField(blank=True, max_length=17),
        ),
        migrations.CreateModel(
            name="HotspotDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mac_address", models.CharField(max_length=17, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("purchase", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="devices", to="hotspot.purchase")),
            ],
            options={"ordering": ["created_at"]},
        ),
    ]
