from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from pathlib import Path

from .database import Database
from .paths import bootstrap_pairing_path


BROWSER_EXTENSION_ORIGIN = re.compile(
    r"^(?:chrome-extension://[a-p]{32}|moz-extension://[0-9a-f]{8}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
    re.IGNORECASE,
)
# Kept as a source-compatible alias for the 0.6 API server and tests.
CHROME_EXTENSION_ORIGIN = BROWSER_EXTENSION_ORIGIN


class PairingError(ValueError):
    pass


class PairingManager:
    def __init__(
        self,
        database: Database,
        bootstrap_path: str | Path | None = None,
    ) -> None:
        self.database = database
        self.bootstrap_path = (
            Path(bootstrap_path) if bootstrap_path is not None else bootstrap_pairing_path()
        )

    @property
    def pairing_code(self) -> str:
        return self.database.ensure_pairing_code()

    @property
    def paired_origin(self) -> str | None:
        value = self.database.get_setting("extension_origin")
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def pair(self, origin: str, code: str) -> str:
        if not CHROME_EXTENSION_ORIGIN.fullmatch(origin):
            raise PairingError("只允许 Chrome、Edge 或 Firefox 扩展进行配对")
        if not hmac.compare_digest(str(code), self.pairing_code):
            raise PairingError("配对码不正确")

        return self._issue_token(origin)

    def pair_with_bootstrap(self, origin: str, secret: str) -> str:
        if not CHROME_EXTENSION_ORIGIN.fullmatch(origin):
            raise PairingError("只允许 Chrome、Edge 或 Firefox 扩展进行配对")
        try:
            payload = json.loads(self.bootstrap_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise PairingError("自动连接凭据不存在") from None
        expected_hash = payload.get("secretHash") if isinstance(payload, dict) else None
        expires_at = payload.get("expiresAt") if isinstance(payload, dict) else None
        if not isinstance(expected_hash, str) or not isinstance(expires_at, (int, float)):
            raise PairingError("自动连接凭据无效")
        if time.time() > float(expires_at):
            self.bootstrap_path.unlink(missing_ok=True)
            raise PairingError("自动连接凭据已过期")
        actual_hash = hashlib.sha256(str(secret).encode("utf-8")).hexdigest()
        if not hmac.compare_digest(actual_hash, expected_hash):
            raise PairingError("自动配对凭据不正确")

        token = self._issue_token(origin)
        self.bootstrap_path.unlink(missing_ok=True)
        return token

    def recover(self, origin: str) -> str:
        """Reissue a token only to the exact extension origin already registered."""
        if not CHROME_EXTENSION_ORIGIN.fullmatch(origin):
            raise PairingError("只允许 Chrome、Edge 或 Firefox 扩展自动连接")
        existing_origin = self.paired_origin
        if not existing_origin or not hmac.compare_digest(origin, existing_origin):
            raise PairingError("此浏览器扩展尚未在本机登记，无法自动恢复连接")
        return self._issue_token(origin)

    def _issue_token(self, origin: str) -> str:
        existing_origin = self.paired_origin
        if existing_origin and existing_origin != origin:
            raise PairingError("已经与另一个 Chrome 扩展配对，请先在助手中解除配对")
        token = secrets.token_urlsafe(32)
        self.database.set_settings(
            {
                "extension_origin": origin,
                "extension_token_hash": self._token_hash(token),
                "pairing_code": f"{secrets.randbelow(1_000_000):06d}",
            }
        )
        return token

    def authenticate(self, origin: str, token: str) -> bool:
        settings = self.database.get_settings(
            ("extension_origin", "extension_token_hash")
        )
        expected_origin = settings.get("extension_origin")
        expected_hash = settings.get("extension_token_hash")
        if not expected_origin or not isinstance(expected_hash, str):
            return False
        if not hmac.compare_digest(origin, expected_origin):
            return False
        return hmac.compare_digest(self._token_hash(token), expected_hash)

    def unpair(self) -> None:
        self.database.set_settings(
            {
                "extension_origin": None,
                "extension_token_hash": None,
                "pairing_code": f"{secrets.randbelow(1_000_000):06d}",
            }
        )
