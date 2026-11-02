from django.contrib import admin

from .mikrotik import provision_purchase
from .routeros_api import RouterOSError
from .models import HotspotDevice, Location, PassPlan, Purchase, Voucher

admin.site.site_header = "Hotspot owner console"
admin.site.site_title = "Hotspot management"
admin.site.index_title = "Manage packages, payments, and vouchers"


@admin.register(PassPlan)
class PassPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price_kes", "duration_seconds", "device_count", "is_active", "sort_order")
    list_editable = ("price_kes", "is_active", "sort_order")
    list_filter = ("is_active", "device_count")
    search_fields = ("name", "code")
    ordering = ("sort_order", "duration_seconds", "device_count")


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("created_at", "phone_number", "plan", "amount_kes", "status", "access_activated_at", "mpesa_receipt", "expires_at")
    list_filter = ("status", "plan", "access_activated_at", "created_at")
    search_fields = ("phone_number", "mpesa_receipt", "checkout_request_id")
    readonly_fields = (
        "public_id", "plan", "phone_number", "device_mac", "amount_kes", "merchant_request_id",
        "checkout_request_id", "mpesa_receipt", "router_username", "router_password",
        "payment_error", "access_error", "created_at", "paid_at", "expires_at", "access_activated_at",
    )

    actions = ["provision_access"]

    @admin.action(description="Provision Wi-Fi access on MikroTik router")
    def provision_access(self, request, queryset):
        success = 0
        for purchase in queryset.filter(status=Purchase.Status.PAID):
            try:
                if provision_purchase(purchase):
                    success += 1
            except RouterOSError as exc:
                self.message_user(request, f"Error provisioning {purchase.phone_number}: {exc}", level="error")
        self.message_user(request, f"Successfully provisioned {success} purchase(s).")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method == "GET" and super().has_change_permission(request, obj)


@admin.register(Voucher)
class VoucherAdmin(admin.ModelAdmin):
    list_display = ("code", "plan", "status", "created_at", "redeemed_at")
    list_filter = ("status", "plan", "created_at")
    search_fields = ("code",)
    readonly_fields = ("created_at", "redeemed_at", "purchase")


@admin.register(HotspotDevice)
class HotspotDeviceAdmin(admin.ModelAdmin):
    list_display = ("mac_address", "purchase", "created_at")
    search_fields = ("mac_address", "purchase__phone_number", "purchase__mpesa_receipt")
    readonly_fields = ("purchase", "mac_address", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "support_phone", "is_active")
    list_editable = ("support_phone", "is_active")
    search_fields = ("name", "slug")
