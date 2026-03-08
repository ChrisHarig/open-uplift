"""Tests for encrypted API key storage."""

import pytest

from open_uplift.keystore import (
    delete_api_key,
    get_api_key,
    list_api_keys,
    store_api_key,
)


@pytest.fixture(autouse=True)
def _patch_keyfile(tmp_path, monkeypatch):
    """Use a temp keyfile so tests don't touch real data."""
    monkeypatch.setattr("open_uplift.keystore.DATA_DIR", tmp_path)
    monkeypatch.setattr("open_uplift.keystore.KEYFILE_PATH", tmp_path / ".keyfile")


def test_store_and_retrieve(db):
    store_api_key(db, "anthropic", "default", "sk-ant-test-123")
    db.commit()

    key = get_api_key(db, "anthropic", "default")
    assert key == "sk-ant-test-123"


def test_retrieve_first_key_for_provider(db):
    store_api_key(db, "anthropic", "default", "sk-first")
    db.commit()

    key = get_api_key(db, "anthropic", "default")
    assert key == "sk-first"


def test_retrieve_nonexistent_key(db):
    key = get_api_key(db, "anthropic", "nope")
    assert key is None


def test_delete_key(db):
    store_api_key(db, "openai", "default", "sk-openai-123")
    db.commit()

    deleted = delete_api_key(db, "openai", "default")
    assert deleted is True

    key = get_api_key(db, "openai", "default")
    assert key is None


def test_delete_nonexistent_key(db):
    deleted = delete_api_key(db, "openai", "nope")
    assert deleted is False


def test_list_keys(db):
    store_api_key(db, "anthropic", "key1", "sk-1")
    store_api_key(db, "openai", "key2", "sk-2")
    db.commit()

    all_keys = list_api_keys(db)
    assert len(all_keys) == 2
    # Should not contain raw key
    for k in all_keys:
        assert "encrypted_key" not in k
        assert "provider" in k
        assert "key_name" in k


def test_list_keys_by_provider(db):
    store_api_key(db, "anthropic", "key1", "sk-1")
    store_api_key(db, "openai", "key2", "sk-2")
    db.commit()

    anthropic_keys = list_api_keys(db, provider="anthropic")
    assert len(anthropic_keys) == 1
    assert anthropic_keys[0]["provider"] == "anthropic"


def test_encryption_roundtrip(db):
    """Key should survive encrypt -> store -> retrieve -> decrypt."""
    original = "sk-ant-api03-very-long-key-with-special-chars!@#$%"
    store_api_key(db, "anthropic", "test", original)
    db.commit()

    retrieved = get_api_key(db, "anthropic", "test")
    assert retrieved == original


def test_overwrite_key(db):
    store_api_key(db, "anthropic", "default", "old-key")
    db.commit()
    store_api_key(db, "anthropic", "default", "new-key")
    db.commit()

    key = get_api_key(db, "anthropic", "default")
    assert key == "new-key"

    # Should still be only one key
    keys = list_api_keys(db, provider="anthropic")
    assert len(keys) == 1
