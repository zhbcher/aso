# _lib/lock_utils.py -- Cross-platform file locking
# Replaces fcntl (Unix-only) with auto-detection: msvcrt (Windows) / fcntl (Unix) / filelock (fallback)
# Usage: all .skill files that need file locking call acquire_lock/release_lock from here.

import os
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress

# Detect available locking mechanism
try:
    import fcntl  # Unix  # type: ignore[import-untyped]
    _LOCK_BACKEND = "fcntl"
except ImportError:
    try:
        import msvcrt  # type: ignore[import-untyped]  # Windows
        _LOCK_BACKEND = "msvcrt"
    except ImportError:
        try:
            import filelock  # Cross-platform
            _LOCK_BACKEND = "filelock"
        except ImportError:
            try:
                import portalocker  # type: ignore[import-untyped]  # Legacy fallback
                _LOCK_BACKEND = "portalocker"
            except ImportError:
                _LOCK_BACKEND = "none"


@contextmanager
def file_lock(lock_path: str, timeout: float = 30.0) -> Generator[int, None, None]:
    """Context manager for cross-platform file locking.

    Supports fcntl (Unix), msvcrt (Windows), filelock (cross-platform pip),
    and portalocker (legacy fallback).

    Args:
        lock_path: Path to the lock file (created if not exists).
        timeout: Maximum seconds to wait for the lock.

    Yields:
        file descriptor (int) when locked, or -1 if no locking available.

    Raises:
        TimeoutError if lock cannot be acquired within timeout.
    """
    if _LOCK_BACKEND == "none":
        # No locking available -- proceed without lock (best-effort)
        yield -1
        return

    if _LOCK_BACKEND == "filelock":
        # Use filelock library which is cross-platform and robust
        lock = filelock.FileLock(lock_path, timeout=timeout)
        try:
            lock.acquire(timeout=timeout)
            # Create the file if not exists so we can yield a fd
            fd = os.open(lock_path, os.O_RDONLY)
            yield fd
        except filelock.Timeout as exc:
            raise TimeoutError(
                f"Could not acquire lock on {lock_path} within {timeout}s"
            ) from exc
        finally:
            with suppress(Exception):
                os.close(fd)
            if lock.is_locked:
                lock.release()
        return

    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    deadline = time.time() + timeout

    try:
        while True:
            try:
                _acquire(lock_fd)
                break
            except OSError:
                if time.time() > deadline:
                    os.close(lock_fd)
                    raise TimeoutError(
                        f"Could not acquire lock on {lock_path} within {timeout}s"
                    ) from None
                time.sleep(0.1)

        yield lock_fd
    finally:
        with suppress(OSError):
            _release(lock_fd)
        with suppress(OSError):
            os.close(lock_fd)


def _acquire(fd: int) -> None:
    """Acquire exclusive lock on file descriptor."""
    if _LOCK_BACKEND == "fcntl":
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif _LOCK_BACKEND == "msvcrt":
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
    elif _LOCK_BACKEND == "portalocker":
        portalocker.lock(fd, portalocker.LOCK_EX | portalocker.LOCK_NB)  # type: ignore[attr-defined]


def _release(fd: int) -> None:
    """Release lock on file descriptor."""
    if _LOCK_BACKEND == "fcntl":
        fcntl.flock(fd, fcntl.LOCK_UN)
    elif _LOCK_BACKEND == "msvcrt":
        from contextlib import suppress
        with suppress(OSError):
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
    elif _LOCK_BACKEND == "portalocker":
        portalocker.unlock(fd)  # type: ignore[attr-defined]


def get_lock_backend() -> str:
    """Return the name of the active locking backend."""
    return _LOCK_BACKEND


def is_locking_available() -> bool:
    """Return True if a locking backend is available."""
    return _LOCK_BACKEND != "none"
