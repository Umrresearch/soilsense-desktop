"""
Login — passwords are checked with bcrypt, the same hashes the website stores.

bcrypt.checkpw hashes what was typed using the salt inside the stored hash and compares
the results. The real password is never stored or compared directly.
"""
import bcrypt

from . import db

_DUMMY = b"$2b$10$CwTycUXWue0Thq9StjUM0uJ8.6m0p3bqdDeeA3A0eTq1J4yZ5rqKS"   # keeps timing the same for unknown users


def login(identifier, password):
    """Return the farmer (without the hash) or None."""
    if not identifier.strip() or not password:
        return None
    farmer = db.farmer_for_login(identifier)
    stored = (farmer or {}).get("password_hash") or _DUMMY.decode()
    stored = stored.encode()
    try:
        ok = bcrypt.checkpw(password.encode(), stored)
    except ValueError:
        ok = False
    if not farmer or not ok:
        return None
    farmer.pop("password_hash", None)
    return farmer
