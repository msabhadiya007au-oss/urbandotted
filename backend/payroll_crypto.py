"""Bank-detail encryption helper for Payroll.

Uses Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from the
PAYROLL_ENC_KEY environment variable. The raw env value can be any string;
we PBKDF2-HMAC-SHA256 it into a 32-byte key. Rotating the key requires
re-encrypting existing values via a migration.

Only account_number and BSB full values are encrypted at rest.
Masked short forms are stored in plaintext for display.
Full values are ONLY decrypted for `owner` role requests and audit-logged.
"""
from __future__ import annotations

import base64
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_SALT = b"urbandotted-payroll-v1"  # constant per deployment; not a secret
_ITERATIONS = 200_000
_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    raw = (os.environ.get("PAYROLL_ENC_KEY") or "").strip()
    if not raw:
        raise RuntimeError(
            "PAYROLL_ENC_KEY is not set. Add a long random string to the backend"
            " environment (e.g. `openssl rand -hex 48`) before using bank details."
        )
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_SALT,
                     iterations=_ITERATIONS)
    key = base64.urlsafe_b64encode(kdf.derive(raw.encode("utf-8")))
    _fernet = Fernet(key)
    return _fernet


def encrypt(plain: str) -> str:
    if plain is None or plain == "":
        return ""
    return _get_fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise RuntimeError("Bank detail could not be decrypted; PAYROLL_ENC_KEY may have changed")


def mask_account(number: str) -> str:
    """Return `****1234` style. Handles empty and short values safely."""
    s = "".join(ch for ch in (number or "") if ch.isdigit())
    if not s:
        return ""
    if len(s) <= 4:
        return "*" * len(s)
    return "*" * (len(s) - 4) + s[-4:]


def mask_bsb(bsb: str) -> str:
    """BSB is 6 digits usually formatted `NNN-NNN`. Mask first three."""
    s = "".join(ch for ch in (bsb or "") if ch.isdigit())
    if not s:
        return ""
    if len(s) <= 3:
        return "*" * len(s)
    return "***-" + s[-3:] if len(s) == 6 else "*" * (len(s) - 3) + s[-3:]


def mask_tfn(tfn: str) -> str:
    """AU TFN is 8 or 9 digits. Show last 3."""
    s = "".join(ch for ch in (tfn or "") if ch.isdigit())
    if not s:
        return ""
    if len(s) <= 3:
        return "*" * len(s)
    return "*" * (len(s) - 3) + s[-3:]
