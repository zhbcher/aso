"""PII masking utilities for ASO traces — production-grade.

Supports:
- Phone numbers (international and domestic)
- Email addresses
- API keys, tokens, secrets
- IP addresses (IPv4 and IPv6)
- URLs (full URLs and domain names)
- Chinese ID numbers (18-digit)
- Credit card numbers
- Passwords and auth tokens
- File paths that may leak system info
- Usernames / login IDs in common formats

Usage:
    from _lib.pii_mask import mask, unmask, mask_with_log
    clean = mask(raw_text)
    logging_clean = mask_with_log(raw_text, "user_input")
"""

from __future__ import annotations

import re

# === Replacement constants ===
_REDACTED = "<REDACTED>"
_REDACTED_PHONE = "<REDACTED_PHONE>"
_REDACTED_EMAIL = "<REDACTED_EMAIL>"
_REDACTED_KEY = "<REDACTED_KEY>"
_REDACTED_IP = "<REDACTED_IP>"
_REDACTED_URL = "<REDACTED_URL>"
_REDACTED_ID = "<REDACTED_ID>"
_REDACTED_CC = "<REDACTED_CC>"
_REDACTED_PASSWORD = "<REDACTED_PASSWORD>"
_REDACTED_PATH = "<REDACTED_PATH>"
_REDACTED_USERNAME = "<REDACTED_USERNAME>"

# === Pattern definitions ===

# Phone numbers: international (+xx) and domestic formats
_PHONE = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,5}\)?[-.\s]?){2,4}\d{3,5}(?!\d)",
)

# Email addresses
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# API keys, tokens, secrets, passwords
_KEY = re.compile(
    r"(?i)(?:sk|key|token|secret|api|passwd|password|auth|bearer|jwt|access|refresh)"
    r"[-_]?(?:\s*[:=]\s*)?['\"]?[A-Za-z0-9_\-/+=]{8,64}['\"]?"
)

# IPv4 addresses
_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b")

# IPv6 addresses (simplified)
_IPV6 = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
    r"|\b(?:[0-9a-fA-F]{1,4}:){1,7}:"
    r"|\b(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}\b"
    r"|\b::(?:[0-9a-fA-F]{1,4}:){1,6}[0-9a-fA-F]{1,4}\b"
)

# URLs (http/https)
_URL = re.compile(r"https?://[^\s<>\"']+")

# Chinese ID numbers (18-digit with checksum)
_CHINESE_ID = re.compile(r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b")

# Credit card numbers (major providers)
_CC = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")

# Passwords in common formats (password=..., pass=..., pwd=...)
_PASSWORD = re.compile(
    r"(?i)(?:password|passwd|pwd|passphrase)\s*[:=]\s*['\"]?[A-Za-z0-9!@#$%^&*()_+\-=\[\]{}|;:',.<>?/`~]{4,64}['\"]?"
)

# File paths that may leak system info (Unix: /home/..., /Users/...; Windows: C:\Users\...)
_PATH = re.compile(
    r"(?:/[A-Za-z0-9_\-]+){2,}"  # Unix paths
    r"|(?:[A-Za-z]:\\(?:[A-Za-z0-9_\-]+\\)*[A-Za-z0-9_\-]+)"  # Windows paths
)

# Usernames in common formats (user=..., username=..., login=...)
_USERNAME = re.compile(
    r"(?i)(?:user|username|login|handle|nickname)\s*[:=]\s*['\"]?[A-Za-z0-9_.\-]{3,32}['\"]?"
)

# === Combined pattern for all-at-once masking ===
_ALL_PATTERNS: dict[re.Pattern, str] = {
    _PASSWORD: _REDACTED_PASSWORD,
    _CC: _REDACTED_CC,
    _CHINESE_ID: _REDACTED_ID,
    _KEY: _REDACTED_KEY,
    _EMAIL: _REDACTED_EMAIL,
    _PHONE: _REDACTED_PHONE,
    _IPV4: _REDACTED_IP,
    _IPV6: _REDACTED_IP,
    _URL: _REDACTED_URL,
    _PATH: _REDACTED_PATH,
    _USERNAME: _REDACTED_USERNAME,
}


def mask(text: str, patterns: dict[re.Pattern, str] | None = None) -> str:
    """Mask all PII in the given text.

    Args:
        text: Raw text to sanitize.
        patterns: Optional custom pattern->replacement mapping.
                  Defaults to all built-in patterns.

    Returns:
        Sanitized text with PII replaced by placeholders.
    """
    if not text:
        return text
    patterns = patterns or _ALL_PATTERNS
    for pattern, replacement in patterns.items():
        text = pattern.sub(replacement, text)
    return text


def unmask(text: str) -> str:
    """Placeholder: no reversible token map.

    In production, PII reports should reference original trace IDs
    rather than trying to reconstruct masked data.
    """
    return text


def mask_with_log(text: str, context: str = "") -> str:
    """Mask text and log which patterns were triggered.

    Args:
        text: Raw text to sanitize.
        context: Optional description of the source (e.g. "user_input").

    Returns:
        Sanitized text.
    """
    if not text:
        return text
    triggered: set[str] = set()
    result = text
    for pattern, replacement in _ALL_PATTERNS.items():
        if pattern.search(result):
            triggered.add(replacement)
        result = pattern.sub(replacement, result)
    if triggered:
        import logging
        logging.getLogger("aso.pii").info(
            "PII mask triggered in %s: %s", context or "unknown", ", ".join(sorted(triggered))
        )
    return result


def detect_pii(text: str) -> dict[str, int]:
    """Detect PII patterns without masking.

    Args:
        text: Text to scan.

    Returns:
        Dict mapping pattern name to count of matches.
    """
    if not text:
        return {}
    results: dict[str, int] = {}
    pattern_names: dict[int, str] = {
        id(_PHONE): "phone",
        id(_EMAIL): "email",
        id(_KEY): "api_key/token",
        id(_IPV4): "ipv4",
        id(_IPV6): "ipv6",
        id(_URL): "url",
        id(_CHINESE_ID): "chinese_id",
        id(_CC): "credit_card",
        id(_PASSWORD): "password",
        id(_PATH): "file_path",
        id(_USERNAME): "username",
    }
    for pattern in _ALL_PATTERNS:
        count = len(pattern.findall(text))
        if count > 0:
            results[pattern_names.get(id(pattern), "unknown")] = count
    return results


# === Convenience: mask everything with a single generic replacement ===
_SIMPLE_PATTERNS: dict[re.Pattern, str] = {p: _REDACTED for p in _ALL_PATTERNS}


def mask_simple(text: str) -> str:
    """Mask all PII with a single <REDACTED> placeholder.

    Use this when you don't care about distinguishing PII types.
    """
    return mask(text, patterns=_SIMPLE_PATTERNS)
