# _lib/manifest_utils.py -- Shared manifest CRUD operations
# Eliminates _load_manifest / _load_all_manifests / _update_manifest_status
# duplication between deploy.skill and rollback.skill

import json
import os
from typing import Optional
from _lib.path_utils import MANIFESTS_FILE
from _lib.lock_utils import file_lock
from _lib.time_utils import utcnow_iso


def load_manifest(manifest_id: str) -> Optional[dict]:
    """Find a manifest by its ID. Returns None if not found."""
    for m in load_all_manifests():
        if m.get("manifest_id") == manifest_id:
            return m
    return None


def load_all_manifests() -> list[dict]:
    """Load all manifests from the JSON store. Returns [] on error."""
    if not MANIFESTS_FILE.exists():
        return []
    try:
        with open(MANIFESTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return []


def store_manifest(manifest_id: str, manifest: dict) -> bool:
    """Append a new manifest to the JSON store with file locking."""
    from _lib.path_utils import STATE_DIR
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = str(MANIFESTS_FILE) + ".lock"
    try:
        with file_lock(lock_path, timeout=10):
            manifests = []
            if MANIFESTS_FILE.exists():
                with open(MANIFESTS_FILE, "r", encoding="utf-8") as f:
                    manifests = json.load(f)
            manifests.append(manifest)
            # P2-L fix: Atomic write
            tmp_path = str(MANIFESTS_FILE) + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(manifests, f, indent=2, default=str, ensure_ascii=False)
            os.replace(tmp_path, str(MANIFESTS_FILE))
        return True
    except (IOError, json.JSONDecodeError, TimeoutError):
        return False


def update_manifest_status(manifest_id: str, new_status: str, extra_fields: Optional[dict] = None) -> bool:
    """Update a manifest's status with file locking.

    Args:
        manifest_id: The manifest to update.
        new_status: e.g. "deployed", "rolled_back", "failed".
        extra_fields: Optional dict of additional fields to set (e.g. {"rolled_back_at": ...}).
    """
    lock_path = str(MANIFESTS_FILE) + ".lock"
    try:
        with file_lock(lock_path, timeout=10):
            if not MANIFESTS_FILE.exists():
                return False
            with open(MANIFESTS_FILE, "r", encoding="utf-8") as f:
                manifests = json.load(f)
            for m in manifests:
                if m.get("manifest_id") == manifest_id:
                    m["status"] = new_status
                    m["updated_at"] = utcnow_iso()
                    if extra_fields:
                        m.update(extra_fields)
                    break
            # P2-L fix: Atomic write
            tmp_path = str(MANIFESTS_FILE) + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(manifests, f, indent=2, default=str, ensure_ascii=False)
            os.replace(tmp_path, str(MANIFESTS_FILE))
        return True
    except (IOError, json.JSONDecodeError, TimeoutError):
        return False
