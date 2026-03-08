"""Encrypted API key storage using Fernet symmetric encryption."""

import os
import sqlite3
from datetime import datetime, timezone

from cryptography.fernet import Fernet

from open_uplift.config import DATA_DIR


KEYFILE_PATH = DATA_DIR / ".keyfile"


def _get_fernet() -> Fernet:
    """Get or create the Fernet encryption key from ~/.open-uplift/.keyfile."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if KEYFILE_PATH.exists():
        key = KEYFILE_PATH.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        KEYFILE_PATH.write_bytes(key)
        # Restrict permissions to owner only
        os.chmod(str(KEYFILE_PATH), 0o600)
    return Fernet(key)


def store_api_key(
    db: sqlite3.Connection,
    provider: str,
    key_name: str,
    api_key: str,
) -> None:
    """Encrypt and store an API key."""
    f = _get_fernet()
    encrypted = f.encrypt(api_key.encode()).decode()
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """INSERT INTO api_keys (provider, key_name, encrypted_key, created_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(provider, key_name) DO UPDATE SET
               encrypted_key = excluded.encrypted_key,
               created_at = excluded.created_at""",
        (provider, key_name, encrypted, now),
    )


# Standard env var names per provider
PROVIDER_ENV_VARS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def get_api_key(
    db: sqlite3.Connection,
    provider: str,
    key_name: str | None = None,
) -> str | None:
    """Retrieve an API key. Checks stored keys first, then falls back to environment variables."""
    f = _get_fernet()
    if key_name:
        row = db.execute(
            "SELECT encrypted_key FROM api_keys WHERE provider = ? AND key_name = ?",
            (provider, key_name),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT encrypted_key FROM api_keys WHERE provider = ? ORDER BY created_at LIMIT 1",
            (provider,),
        ).fetchone()

    if row:
        # Update last_used_at
        now = datetime.now(timezone.utc).isoformat()
        if key_name:
            db.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE provider = ? AND key_name = ?",
                (now, provider, key_name),
            )
        else:
            db.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE provider = ? AND rowid = (SELECT rowid FROM api_keys WHERE provider = ? ORDER BY created_at LIMIT 1)",
                (now, provider, provider),
            )
        return f.decrypt(row["encrypted_key"].encode()).decode()

    # Fall back to environment variable
    env_var = PROVIDER_ENV_VARS.get(provider)
    if env_var:
        return os.environ.get(env_var)

    return None


def list_api_keys(
    db: sqlite3.Connection,
    provider: str | None = None,
) -> list[dict]:
    """List stored API keys (never returns the raw key)."""
    if provider:
        rows = db.execute(
            "SELECT provider, key_name, created_at, last_used_at FROM api_keys WHERE provider = ?",
            (provider,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT provider, key_name, created_at, last_used_at FROM api_keys"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_api_key(
    db: sqlite3.Connection,
    provider: str,
    key_name: str,
) -> bool:
    """Delete an API key. Returns True if a row was deleted."""
    cursor = db.execute(
        "DELETE FROM api_keys WHERE provider = ? AND key_name = ?",
        (provider, key_name),
    )
    return cursor.rowcount > 0
