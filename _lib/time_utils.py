# _lib/time_utils.py -- Shared timezone-aware UTC utilities
# Eliminates _utcnow_iso() duplication across deploy/rollback/report/benchmark

import datetime


def utcnow_iso() -> str:
    """Return timezone-aware UTC ISO 8601 string with 'Z' suffix.

    Replaces the deprecated datetime.utcnow() pattern.
    Used by deploy.skill, rollback.skill, report.skill, benchmark.skill.
    """
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
