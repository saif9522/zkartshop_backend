"""
Field-level encryption for sensitive PII — Aadhaar numbers, PAN numbers, bank
account numbers. Encrypted at rest (a raw DB dump or backup never exposes
plaintext); transparently decrypted back to a plain string in Python, so
every serializer/view that already reads `vendor.pan_number` etc. keeps
working exactly as before — only what's actually stored on disk changes.

Uses Fernet (AES-128-CBC + HMAC, authenticated encryption) with a key
derived from FIELD_ENCRYPTION_KEY (falls back to SECRET_KEY in dev so this
never blocks local setup — but a real deployment should set a dedicated key,
since rotating SECRET_KEY would otherwise silently break decryption of
already-stored PII).
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _get_fernet():
    key_material = getattr(settings, "FIELD_ENCRYPTION_KEY", None) or settings.SECRET_KEY
    # Fernet needs a 32-byte urlsafe-base64 key — derive one deterministically
    # from whatever string-ish key material we're given.
    digest = hashlib.sha256(key_material.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class EncryptedCharField(models.CharField):
    """
    A CharField that's encrypted at rest. Transparent in Python — reads
    return the decrypted plaintext, writes encrypt automatically. Doubles
    max_length under the hood since ciphertext is longer than plaintext.
    """

    def __init__(self, *args, **kwargs):
        # Ciphertext (base64, with Fernet's ~60-byte overhead) needs meaningfully
        # more room than the plaintext max_length the field was declared with.
        self._plain_max_length = kwargs.get("max_length", 255)
        kwargs["max_length"] = self._plain_max_length * 2 + 100
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs["max_length"] = self._plain_max_length
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except (InvalidToken, ValueError):
            # Pre-existing plaintext data from before encryption was added —
            # degrade gracefully instead of throwing on every read.
            return value

    def get_prep_value(self, value):
        if value in (None, ""):
            return value
        return _get_fernet().encrypt(str(value).encode()).decode()

    def to_python(self, value):
        return value
