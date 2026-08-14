"""Payroll Phase 1 unit tests — pure functions only.

These match the style of tests/test_calculations.py: they exercise our helpers
without hitting the database. Integration/API tests (mongomock-based) live
separately and are executed by the backend testing agent.
"""
import os
import sys
import pathlib

# Ensure a key is set before importing payroll_crypto
os.environ.setdefault("PAYROLL_ENC_KEY", "test-key-for-payroll-crypto-only-not-secret")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

import payroll_crypto as pc  # noqa: E402


def test_mask_account_short():
    assert pc.mask_account("") == ""
    assert pc.mask_account("12") == "**"
    assert pc.mask_account("1234") == "****"


def test_mask_account_normal():
    assert pc.mask_account("123456789") == "*****6789"
    # non-digits stripped, mask covers all-but-last-four
    assert pc.mask_account("12-34 5678") == "****5678"


def test_mask_bsb_six_digits():
    assert pc.mask_bsb("062000") == "***-000"
    assert pc.mask_bsb("062-000") == "***-000"
    assert pc.mask_bsb("") == ""


def test_encrypt_roundtrip():
    for value in ["", "0", "12345678", "062-000", "u\ud7ffnicode"]:
        token = pc.encrypt(value)
        assert pc.decrypt(token) == value, f"roundtrip failed for {value!r}"


def test_encrypt_produces_new_ciphertext_each_call():
    a = pc.encrypt("secret-account-number")
    b = pc.encrypt("secret-account-number")
    # Fernet uses a random IV -> tokens differ, but both decrypt back correctly
    assert a != b
    assert pc.decrypt(a) == pc.decrypt(b) == "secret-account-number"


def test_decrypt_invalid_token_raises():
    import pytest
    with pytest.raises(RuntimeError):
        pc.decrypt("not-a-real-token")
