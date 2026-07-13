# _lib/lock_utils.py -- Cross-platform file locking for KunlunXiaoZhi
# Replaces fcntl (Unix-only) with auto-detection: msvcrt (Windows) / fcntl (Unix) / portalocker (fallback)
# Usage: all .skill files that need file locking call acquire_lock/release_lock from here.

import os
import time
from contextlib import contextmanager
from typing import Optional

# Detect available locking mechanism
try:
    import fcntl  # Unix
    _LOCK_BACKEND = "fcntl"
except ImportError:
    try:
        import msvcrt  # Windows
        _LOCK_BACKEND = "msvcrt"
    except ImportError:
        try:
            import portalocker  # Cross-platform fallback
            _LOCK_BACKEND = "portalocker"
        except ImportError:
            _LOCK_BACKEND = "none"


@contextmanager
def file_lock(lock_path: str, timeout: float = 30.0):
    """Context manager for cross-platform file locking.

    Args:
        lock_path: Path to the lock file (created if not exists).
        timeout: Maximum seconds to wait for the lock.

    Yields:
        file descriptor (int) when locked.

    Raises:
        TimeoutError if lock cannot be acquired within timeout.
    """
    if _LOCK_BACKEND == "none":
        # No locking available -- proceed without lock (best-effort)
        yield -1
        return

    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    deadline = time.time() + timeout

    try:
        while True:
            try:
                _acquire(lock_fd)
                break
            except (OSError, IOError):
                if time.time() > deadline:
                    os.close(lock_fd)
                    raise TimeoutError(
                        f"Could not acquire lock on {lock_path} within {timeout}s"
                    )
                time.sleep(0.1)

        yield lock_fd
    finally:
        try:
            _release(lock_fd)
        except (OSError, IOError):
            pass
        os.close(lock_fd)


def _acquire(fd: int):
    """Acquire exclusive lock on file descriptor."""
    if _LOCK_BACKEND == "fcntl":
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif _LOCK_BACKEND == "msvcrt":
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    elif _LOCK_BACKEND == "portalocker":
        portalocker.lock(fd, portalocker.LOCK_EX | portalocker.LOCK_NB)


def _release(fd: int):
    """Release lock on file descriptor."""
    if _LOCK_BACKEND == "fcntl":
        fcntl.flock(fd, fcntl.LOCK_UN)
    elif _LOCK_BACKEND == "msvcrt":
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    elif _LOCK_BACKEND == "portalocker":
        portalocker.unlock(fd)


def get_lock_backend() -> str:
    """Return the name of the active locking backend."""
    return _LOCK_BACKEND
