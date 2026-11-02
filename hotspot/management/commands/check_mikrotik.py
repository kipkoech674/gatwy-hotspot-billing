import os

from django.core.management.base import BaseCommand, CommandError

from hotspot.routeros_api import RouterOSAPI, RouterOSError


class Command(BaseCommand):
    help = "Check the configured local MikroTik API connection without changing router settings."

    def handle(self, *args, **options):
        host = os.environ.get("MIKROTIK_HOST", "").strip()
        username = os.environ.get("MIKROTIK_USERNAME", "").strip()
        password = os.environ.get("MIKROTIK_PASSWORD", "")
        port = os.environ.get("MIKROTIK_PORT", "8728")
        if not host or not username or not password:
            raise CommandError("Set MIKROTIK_HOST, MIKROTIK_USERNAME, and MIKROTIK_PASSWORD in this PowerShell session first.")
        try:
            with RouterOSAPI(host, username, password, port=port) as router:
                resources = router.command("/system/resource/print")
        except (RouterOSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        if not resources:
            raise CommandError("RouterOS API connected but returned no system resource details.")
        resource = resources[0]
        self.stdout.write(self.style.SUCCESS("MikroTik API connection succeeded."))
        self.stdout.write(f"RouterOS version: {resource.get('version', 'unknown')}")
        self.stdout.write(f"Board: {resource.get('board-name', 'unknown')}")
        self.stdout.write(f"Free memory: {resource.get('free-memory', 'unknown')} bytes")
