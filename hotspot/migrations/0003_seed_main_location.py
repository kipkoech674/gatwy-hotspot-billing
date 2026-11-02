from django.db import migrations


def seed_location(apps, schema_editor):
    Location = apps.get_model("hotspot", "Location")
    Location.objects.get_or_create(
        slug="main",
        defaults={"name": "Main location", "support_phone": "+254716719022", "is_active": True},
    )


def unseed_location(apps, schema_editor):
    Location = apps.get_model("hotspot", "Location")
    Location.objects.filter(slug="main").delete()


class Migration(migrations.Migration):
    dependencies = [("hotspot", "0002_seed_pass_plans")]
    operations = [migrations.RunPython(seed_location, unseed_location)]
