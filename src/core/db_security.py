# -*- coding: utf-8 -*-
"""
Database encryption password management.

Stores the SQLCipher encryption password in the OS keyring (macOS Keychain)
so the user does not need to re-enter it on every app startup.  A permission-
protected file fallback is used when the keyring backend is unavailable.
"""
import os
import logging

logger = logging.getLogger(__name__)

SERVICE_NAME = "task-sheet-automation"
KEY_NAME = "db-encryption"

# In-memory cache so we don't hit the keyring on every RepositoryDB() call.
_cached_password = None

# Fallback file path (only used if keyring is unavailable).
_FALLBACK_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
_FALLBACK_FILE = os.path.join(_FALLBACK_DIR, ".db_key")


def _try_keyring_get():
    """Attempt to read the password from the OS keyring."""
    try:
        import keyring
        return keyring.get_password(SERVICE_NAME, KEY_NAME)
    except Exception as exc:
        logger.warning("Keyring get failed: %s", exc)
        return None


def _try_keyring_set(password):
    """Attempt to store the password in the OS keyring."""
    try:
        import keyring
        keyring.set_password(SERVICE_NAME, KEY_NAME, password)
        return True
    except Exception as exc:
        logger.warning("Keyring set failed: %s", exc)
        return False


def _fallback_get():
    """Read password from the permission-protected fallback file."""
    if not os.path.isfile(_FALLBACK_FILE):
        return None
    try:
        with open(_FALLBACK_FILE, "r") as fh:
            return fh.read().strip()
    except OSError as exc:
        logger.warning("Fallback key read failed: %s", exc)
        return None


def _fallback_set(password):
    """Write password to the fallback file with 0600 permissions."""
    os.makedirs(_FALLBACK_DIR, exist_ok=True)
    with open(_FALLBACK_FILE, "w") as fh:
        fh.write(password)
    os.chmod(_FALLBACK_FILE, 0o600)


def get_password():
    """Return the cached/keyring/fallback password, or None if not set."""
    global _cached_password
    if _cached_password is not None:
        return _cached_password

    pwd = _try_keyring_get()
    if pwd:
        _cached_password = pwd
        return pwd

    pwd = _fallback_get()
    if pwd:
        _cached_password = pwd
        logger.info("Using fallback key file (keyring unavailable).")
        return pwd

    return None


def set_password(password):
    """Store *password* in keyring (with file fallback) and cache it."""
    global _cached_password
    if not password:
        raise ValueError("Password must not be empty.")

    if _try_keyring_set(password):
        # Clean up fallback file if it exists — keyring is working.
        if os.path.isfile(_FALLBACK_FILE):
            try:
                os.remove(_FALLBACK_FILE)
            except OSError:
                pass
    else:
        _fallback_set(password)

    _cached_password = password
    logger.info("Encryption password stored.")


def has_password():
    """Return True if a password is available (cached, keyring, or fallback)."""
    return get_password() is not None


def clear_cache():
    """Clear the in-memory cache (forces next get_password() to hit keyring)."""
    global _cached_password
    _cached_password = None
