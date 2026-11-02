from django.db import migrations


PLANS = [
    ("hour-1", "1 hour", 3600, 10, 1, 10),
    ("hours-3", "3 hours", 10800, 20, 1, 20),
    ("hours-12", "12 hours", 43200, 40, 1, 30),
    ("day-1", "24 hours", 86400, 50, 1, 40),
    ("days-7", "7 days", 604800, 250, 1, 50),
    ("days-14", "14 days", 1209600, 300, 1, 60),
    ("days-14-two-devices", "14 days · 2 devices", 1209600, 400, 2, 70),
    ("days-30", "30 days", 2592000, 600, 1, 80),
    ("days-30-two-devices", "30 days · 2 devices", 2592000, 750, 2, 90),
]


def seed(apps, schema_editor):
    PassPlan = apps.get_model("hotspot", "PassPlan")
    for code, name, duration, price, devices, order in PLANS:
        PassPlan.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "duration_seconds": duration,
                "price_kes": price,
                "device_count": devices,
                "sort_order": order,
                "is_active": True,
            },
        )


def unseed(apps, schema_editor):
    PassPlan = apps.get_model("hotspot", "PassPlan")
    PassPlan.objects.filter(code__in=[plan[0] for plan in PLANS]).delete()


class Migration(migrations.Migration):
    dependencies = [("hotspot", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
