"""_lib/exceptions.py — Custom exception hierarchy for ASO.

Replaces generic RuntimeError usage with typed exceptions.
Allows different fallback/retry strategies per exception type.
"""

from __future__ import annotations


class ASOError(Exception):
    """Base exception for all ASO errors."""


# === LLM / Provider errors ===


class LLMProviderError(ASOError):
    """Base class for LLM provider errors."""


class LLMTimeoutError(LLMProviderError):
    """LLM call timed out."""


class LLMRateLimitError(LLMProviderError):
    """Rate limited (HTTP 429) by the provider."""


class LLMAuthError(LLMProviderError):
    """Authentication failure (invalid API key)."""


class LLMQuotaExceededError(LLMProviderError):
    """Quota exceeded (insufficient balance)."""


class LLMContentPolicyError(LLMProviderError):
    """Content policy violation."""


class LLMConnectionError(LLMProviderError):
    """Connection-level failure (DNS, network, etc.)."""


class LLMEmptyResponseError(LLMProviderError):
    """LLM returned an empty response."""


# === Parse errors ===


class JSONParseError(ASOError):
    """Failed to parse JSON from LLM response."""


class SchemaValidationError(ASOError):
    """Data does not conform to expected schema."""


# === Pipeline errors ===


class PipelineBudgetError(ASOError):
    """Pipeline budget (time/tokens/cost) exceeded."""


class SandboxBudgetError(PipelineBudgetError):
    """Budget exceeded inside sandbox evaluation."""


class GateRejectedError(ASOError):
    """Candidate was rejected by the gate."""


class TargetDeniedError(ASOError):
    """Target is denied by evolution-policy."""


class CircuitBreakerOpenError(ASOError):
    """Circuit breaker is open for this target."""


# === File / IO errors ===


class FileLockTimeoutError(ASOError):
    """Could not acquire file lock within timeout."""


class AtomicWriteError(ASOError):
    """Atomic file write failed."""


# === Snapshot errors ===


class SnapshotError(ASOError):
    """Snapshot operation failed."""


class RollbackError(ASOError):
    """Rollback operation failed."""


# === Config errors ===


class ConfigError(ASOError):
    """Configuration loading or validation error."""


def classify_llm_error(error_message: str) -> LLMProviderError:
    """Classify an HTTP/API error message into a typed exception.

    Args:
        error_message: The error message or description.

    Returns:
        An appropriate typed LLMProviderError subclass.
    """
    msg = error_message.lower()
    if "429" in msg or "rate limit" in msg or "too many requests" in msg:
        return LLMRateLimitError(error_message)
    if "401" in msg or "403" in msg or "invalid_api_key" in msg or "unauthorized" in msg:
        return LLMAuthError(error_message)
    if "402" in msg or "insufficient_balance" in msg or "quota" in msg or "payment" in msg:
        return LLMQuotaExceededError(error_message)
    if "content_policy" in msg or "content_filter" in msg or "content policy" in msg:
        return LLMContentPolicyError(error_message)
    if "timeout" in msg or "timed out" in msg:
        return LLMTimeoutError(error_message)
    if "connection" in msg or "dns" in msg or "resolve" in msg:
        return LLMConnectionError(error_message)
    if "empty" in msg and "response" in msg:
        return LLMEmptyResponseError(error_message)
    return LLMProviderError(error_message)
