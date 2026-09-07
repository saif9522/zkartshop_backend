import base64

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.core.management.base import BaseCommand
from py_vapid import Vapid


class Command(BaseCommand):
    help = "Generates a VAPID keypair for Web Push notifications. Run once, put the output in your .env file."

    def handle(self, *args, **options):
        vapid = Vapid()
        vapid.generate_keys()

        private_pem = vapid.private_pem().decode()

        # Public key in the raw uncompressed-point base64url form the browser's
        # PushManager.subscribe() applicationServerKey expects.
        raw_public = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        public_b64url = base64.urlsafe_b64encode(raw_public).decode().rstrip("=")

        self.stdout.write(self.style.SUCCESS("VAPID keypair generated. Add these to backend/.env:\n"))
        self.stdout.write(f"VAPID_PUBLIC_KEY={public_b64url}")
        self.stdout.write("VAPID_PRIVATE_KEY_PEM=" + private_pem.replace("\n", "\\n"))
        self.stdout.write(
            "\nAlso add VAPID_PUBLIC_KEY to the customer app's .env as VITE_VAPID_PUBLIC_KEY "
            "(that's the app that actually subscribes to push)."
        )
