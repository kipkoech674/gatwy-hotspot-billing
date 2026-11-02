from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from hotspot.mikrotik import (
    get_router,
    provision_purchase,
    remove_purchase_devices,
    router_configured,
)
from hotspot.models import Purchase
from hotspot.routeros_api import RouterOSError

LOCK_KEY = "lock:sync_mikrotik_access"
LOCK_TIMEOUT_SECONDS = 55


def _is_connection_error(exc):
    """Whether continuing this run would only repeat a router connection failure."""
    message = str(exc).lower()
    return any(
        phrase in message
        for phrase in ("connect", "credential", "authentication", "timed out", "refused")
    )


class Command(BaseCommand):
    help = "Provision paid HotSpot accounts and remove expired ones. Run once per minute."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log accounts that would be activated or removed without modifying the router or database.",
        )

    def handle(self, *args, **options):
        if not router_configured():
            self.stdout.write(self.style.WARNING("MikroTik is not configured; no router accounts were changed."))
            return

        dry_run = options["dry_run"]
        if not dry_run and not cache.add(LOCK_KEY, True, timeout=LOCK_TIMEOUT_SECONDS):
            self.stdout.write(self.style.NOTICE("Another sync_mikrotik_access run is currently in progress. Skipping."))
            return

        try:
            self._run_sync(dry_run)
        finally:
            if not dry_run:
                cache.delete(LOCK_KEY)

    def _run_sync(self, dry_run):
        now = timezone.now()
        activated = 0
        removed = 0
        errors = 0

        # 1. Retry pending paid purchases that have not yet had Wi-Fi access enabled
        pending = Purchase.objects.select_related("plan").filter(
            status=Purchase.Status.PAID,
            expires_at__gt=now,
            access_activated_at__isnull=True,
        )
        for purchase in pending.iterator():
            if not purchase.device_mac:
                purchase.access_error = "Device MAC address is missing."
                purchase.save(update_fields=["access_error"])
                errors += 1
                continue

            if dry_run:
                activated += 1
                continue

            try:
                if provision_purchase(purchase):
                    activated += 1
            except RouterOSError as exc:
                errors += 1
                purchase.access_error = str(exc)[:160]
                purchase.save(update_fields=["access_error"])
                if _is_connection_error(exc):
                    self.stderr.write(self.style.ERROR(f"Router connection failed while provisioning: {exc}"))
                    break

        # 2. Disconnect and expire purchases that have reached their time limit
        expired = Purchase.objects.prefetch_related("devices").filter(
            status=Purchase.Status.PAID,
            expires_at__lte=now,
        )
        for purchase in expired:
            if dry_run:
                removed += 1
                continue

            try:
                remove_purchase_devices(purchase)

                with transaction.atomic():
                    purchase.devices.all().delete()
                    purchase.status = Purchase.Status.EXPIRED
                    purchase.access_error = ""
                    purchase.save(update_fields=["status", "access_error"])
                removed += 1
            except RouterOSError as exc:
                errors += 1
                purchase.access_error = str(exc)[:160]
                purchase.save(update_fields=["access_error"])
                if _is_connection_error(exc):
                    self.stderr.write(self.style.ERROR(f"Router connection failed during expiration: {exc}"))
                    break

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}Activated: {activated}; expired and removed: {removed}; errors: {errors}."))
