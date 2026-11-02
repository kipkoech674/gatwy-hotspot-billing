import uuid

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PassPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=40, unique=True)),
                ("name", models.CharField(max_length=80)),
                ("duration_seconds", models.PositiveIntegerField()),
                ("price_kes", models.PositiveIntegerField(validators=[MinValueValidator(1)])),
                ("device_count", models.PositiveSmallIntegerField(default=1)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["sort_order", "duration_seconds", "device_count"]},
        ),
        migrations.CreateModel(
            name="Location",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
                ("slug", models.SlugField(max_length=40, unique=True)),
                ("support_phone", models.CharField(default="+254716719022", max_length=20)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Purchase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("phone_number", models.CharField(max_length=16)),
                ("amount_kes", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("created", "Created"), ("pending", "Payment requested"), ("paid", "Paid"), ("failed", "Failed"), ("expired", "Expired")], default="created", max_length=12)),
                ("merchant_request_id", models.CharField(blank=True, max_length=100)),
                ("checkout_request_id", models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ("mpesa_receipt", models.CharField(blank=True, max_length=32, null=True, unique=True)),
                ("router_username", models.CharField(blank=True, max_length=64)),
                ("router_password", models.CharField(blank=True, max_length=64)),
                ("payment_error", models.CharField(blank=True, max_length=160)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("access_activated_at", models.DateTimeField(blank=True, null=True)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="purchases", to="hotspot.passplan")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Voucher",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=16, unique=True)),
                ("status", models.CharField(choices=[("unused", "Unused"), ("redeemed", "Redeemed"), ("expired", "Expired"), ("disabled", "Disabled")], default="unused", max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("redeemed_at", models.DateTimeField(blank=True, null=True)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="vouchers", to="hotspot.passplan")),
                ("purchase", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="voucher", to="hotspot.purchase")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
