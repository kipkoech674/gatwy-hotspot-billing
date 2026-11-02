import os
import urllib.error

from django.core.management.base import BaseCommand, CommandError

from hotspot.views import _daraja_access_token, _mpesa_credentials_present


class Command(BaseCommand):
    help = "Verify Daraja configuration and obtain a temporary access token without starting a payment."

    def handle(self, *args, **options):
        required = (
            "MPESA_CONSUMER_KEY",
            "MPESA_CONSUMER_SECRET",
            "MPESA_SHORTCODE",
            "MPESA_PASSKEY",
            "MPESA_CALLBACK_URL",
        )
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise CommandError("Missing .env values: " + ", ".join(missing))
        if not _mpesa_credentials_present():
            raise CommandError("Ensure MPESA_ENVIRONMENT is sandbox or production and MPESA_CALLBACK_URL starts with https://")
        try:
            token = _daraja_access_token()
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
            raise CommandError("Daraja rejected the configuration or could not be reached.") from exc
        if not token:
            raise CommandError("Daraja did not return an access token.")
        env = os.environ.get("MPESA_ENVIRONMENT", "sandbox")
        self.stdout.write(self.style.SUCCESS(f"Daraja {env} credentials are accepted."))
        self.stdout.write("Callback URL: " + os.environ["MPESA_CALLBACK_URL"])
