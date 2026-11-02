import time

from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = "Keep MikroTik access in sync by running the package expiry check every minute."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Seconds between checks (default: 60).",
        )

    def handle(self, *args, **options):
        interval = max(options["interval"], 10)
        self.stdout.write(
            self.style.SUCCESS(
                f"GATWY access worker started. Checking packages every {interval} seconds. Press Ctrl+C to stop."
            )
        )

        try:
            while True:
                try:
                    call_command("sync_mikrotik_access")
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"Access check failed: {exc}"))
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("GATWY access worker stopped."))
