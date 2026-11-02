import uuid

from django.core.validators import MinValueValidator
from django.db import models


class PassPlan(models.Model):
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    duration_seconds = models.PositiveIntegerField()
    price_kes = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    device_count = models.PositiveSmallIntegerField(default=1)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "duration_seconds", "device_count"]

    def __str__(self):
        return f"{self.name} · KSh {self.price_kes:,} · {self.device_count} device(s)"


class Purchase(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PENDING = "pending", "Payment requested"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    plan = models.ForeignKey(PassPlan, on_delete=models.PROTECT, related_name="purchases")
    phone_number = models.CharField(max_length=16)
    device_mac = models.CharField(max_length=17, blank=True)
    amount_kes = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CREATED)
    merchant_request_id = models.CharField(max_length=100, blank=True)
    checkout_request_id = models.CharField(max_length=100, blank=True, unique=True, null=True)
    mpesa_receipt = models.CharField(max_length=32, blank=True, unique=True, null=True)
    router_username = models.CharField(max_length=64, blank=True)
    router_password = models.CharField(max_length=64, blank=True)
    payment_error = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    access_activated_at = models.DateTimeField(null=True, blank=True)
    access_error = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.phone_number} · {self.plan.name} · {self.get_status_display()}"


class HotspotDevice(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="devices")
    mac_address = models.CharField(max_length=17, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.mac_address} / {self.purchase_id}"


class Voucher(models.Model):
    class Status(models.TextChoices):
        UNUSED = "unused", "Unused"
        REDEEMED = "redeemed", "Redeemed"
        EXPIRED = "expired", "Expired"
        DISABLED = "disabled", "Disabled"

    code = models.CharField(max_length=16, unique=True)
    plan = models.ForeignKey(PassPlan, on_delete=models.PROTECT, related_name="vouchers")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNUSED)
    created_at = models.DateTimeField(auto_now_add=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    purchase = models.OneToOneField(Purchase, on_delete=models.SET_NULL, null=True, blank=True, related_name="voucher")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} · {self.plan.name} · {self.get_status_display()}"


class Location(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=40, unique=True)
    support_phone = models.CharField(max_length=20, default="+254716719022")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
