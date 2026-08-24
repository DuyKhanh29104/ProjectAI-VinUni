"""Owner-only local cache for the KITTI delivery-mailbox credential."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path


class KittiImapSecretCacheError(RuntimeError):
    """Raised when a local credential cache is unsafe or malformed."""


def load_kitti_imap_credentials(cache_path: Path) -> tuple[str, str, str, str] | None:
    """Return cached email, host, username and password from an owner-only file."""
    if not cache_path.is_file():
        return None
    mode = stat.S_IMODE(cache_path.stat().st_mode)
    if mode & 0o077:
        raise KittiImapSecretCacheError(
            f"Refusing to read insecure KITTI credential cache {cache_path}; expected permissions 0600."
        )
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise KittiImapSecretCacheError(f"Could not read KITTI credential cache {cache_path}.") from error
    values = tuple(payload.get(field) for field in ("email", "host", "username", "password"))
    if not all(isinstance(value, str) and value for value in values):
        raise KittiImapSecretCacheError(f"KITTI credential cache {cache_path} is malformed.")
    return values  # type: ignore[return-value]


def load_kitti_imap_password(cache_path: Path, *, email: str, host: str, username: str) -> str | None:
    """Return a matching cached password only from an owner-only file."""
    if not cache_path.is_file():
        return None
    mode = stat.S_IMODE(cache_path.stat().st_mode)
    if mode & 0o077:
        raise KittiImapSecretCacheError(
            f"Refusing to read insecure KITTI credential cache {cache_path}; expected permissions 0600."
        )
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise KittiImapSecretCacheError(f"Could not read KITTI credential cache {cache_path}.") from error
    if (payload.get("email"), payload.get("host"), payload.get("username")) != (email, host, username):
        return None
    password = payload.get("password")
    return password if isinstance(password, str) and password else None


def save_kitti_imap_password(cache_path: Path, *, email: str, host: str, username: str, password: str) -> None:
    """Atomically persist a credential cache with 0600 permissions."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"email": email, "host": host, "username": username, "password": password},
        separators=(",", ":"),
    )
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{cache_path.name}.", dir=cache_path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
        temporary_path.chmod(0o600)
        temporary_path.replace(cache_path)
        cache_path.chmod(0o600)
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        raise KittiImapSecretCacheError(f"Could not save KITTI credential cache {cache_path}.") from error
