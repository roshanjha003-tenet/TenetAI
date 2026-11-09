"""Encryption at rest for connector tokens (Fernet: AES-128-CBC + HMAC-SHA256).

The key is TOKEN_ENCRYPTION_KEY (a Fernet key) or, failing that, derived from SECRET_KEY. Rotating
it makes stored tokens unreadable, and people reconnect Google Drive.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings

PREFIX = "enc:"


class TokenBox:
    def __init__(self, settings: Settings) -> None:
        key = (
            settings.token_encryption_key
            or base64.urlsafe_b64encode(
                hashlib.sha256(f"tenet-tokens:{settings.secret_key}".encode()).digest()
            ).decode()
        )
        self.fernet = Fernet(key)

    def seal(self, value: str | None) -> str | None:
        if value is None:
            return None
        return PREFIX + self.fernet.encrypt(value.encode()).decode()

    def open(self, value: str | None) -> str | None:
        if value is None or not value.startswith(PREFIX):
            return value  # stored before encryption was turned on
        try:
            return self.fernet.decrypt(value[len(PREFIX) :].encode()).decode()
        except InvalidToken:
            return None
