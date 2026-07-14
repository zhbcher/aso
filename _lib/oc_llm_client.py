"""_lib/oc_llm_client.py — OpenClaw 版 LLM 调用客户端

适配自 KLXZ evolve-skill-v4 _lib/klzm_client.py。
将 KLXZ 的 klzm-proxy 调用改为直接调用 OpenClaw 配置的 LLM provider。
支持多模型轮换 + fallback 链 + 重试 + 429 退避。

Configuration is now loaded from config.yaml via config_loader.
"""

from __future__ import annotations

import contextlib
import json
import re
import time
import urllib.error
import urllib.request

from _lib.config_loader import get_default, get_fallback_chain, get_pipeline_models, get_providers
from _lib.exceptions import (
    JSONParseError,
    LLMAuthError,
    LLMConnectionError,
    LLMContentPolicyError,
    LLMEmptyResponseError,
    LLMProviderError,
    LLMQuotaExceededError,
    LLMRateLimitError,
    classify_llm_error,
)

# Load config from config.yaml
PROVIDERS = get_providers()
PIPELINE_MODELS = get_pipeline_models()
FALLBACK_CHAIN = get_fallback_chain()

DEFAULT_TIMEOUT = get_default("timeout_seconds", 60)
MAX_RETRIES = get_default("max_retries", 2)
RETRY_DELAY = get_default("retry_delay_seconds", 1.0)
MAX_429_RETRIES = get_default("max_429_retries", 3)
INITIAL_BACKOFF_429 = get_default("initial_backoff_429_seconds", 2.0)
MAX_RETRY_AFTER = get_default("max_retry_after_seconds", 60)


def _get_api_key(provider: str) -> str:
    """Get API key for a given provider from environment variables."""
    import os
    provider_config = PROVIDERS.get(provider)
    if not provider_config:
        return ""
    return os.environ.get(provider_config.get("api_key_env", ""), "")


def _clean_think_tags(text: str) -> str:
    """Remove thinking blocks from model output."""
    if not text:
        return ""
    cleaned = text
    cleaned = re.sub(r"<think>[\s\S]*?<\/think>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<thinking>[\s\S]*?<\/thinking>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<Thought>[\s\S]*?<\/Thought>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _build_request(provider_config: dict, model: str, messages: list, temperature: float, max_tokens: int) -> urllib.request.Request:
    """Build an HTTP request for the LLM API."""
    api_key = _get_api_key(provider_config.get("name", ""))
    if not api_key:
        raise LLMAuthError(f"{provider_config.get('api_key_env', '?')} not set")

    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    return urllib.request.Request(
        provider_config["base_url"],
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )


def call_llm(
    messages: list[dict],
    provider: str = "sensenova",
    model: str = "deepseek-v4-flash",
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Call a single model via OpenAI-compatible API.

    Args:
        messages: OpenAI-format message list.
        provider: Provider name (sensenova, nvidia, deepseek, agnes).
        model: Model name for the provider.
        temperature: Sampling temperature.
        max_tokens: Max output tokens.
        timeout: Request timeout in seconds.

    Returns:
        Model response text.

    Raises:
        LLMProviderError (or subclass) on failure.
    """
    provider_config = PROVIDERS.get(provider)
    if not provider_config:
        raise LLMProviderError(f"Unknown provider: {provider}")

    api_key = _get_api_key(provider)
    if not api_key:
        raise LLMAuthError(f"{provider_config.get('api_key_env', '?')} not set")

    # Build the request (handle provider name lookup by matching config keys)
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    req = urllib.request.Request(
        provider_config["base_url"],
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    last_error: LLMProviderError | None = None
    retry_429_count = 0
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                msg = result.get("choices", [{}])[0].get("message", {})
                content = msg.get("content", "")
                if content:
                    content = _clean_think_tags(content)
                if not content:
                    raise LLMEmptyResponseError("LLM returned empty content after cleaning")
                return content.strip()
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            typed_error = classify_llm_error(f"HTTP {e.code}: {error_body[:200]}")

            # Non-retryable errors
            if isinstance(typed_error, (LLMAuthError, LLMQuotaExceededError, LLMContentPolicyError)):
                raise typed_error from None

            if isinstance(typed_error, LLMRateLimitError) and retry_429_count < MAX_429_RETRIES:
                retry_429_count += 1
                retry_after = INITIAL_BACKOFF_429 * (2 ** (retry_429_count - 1))
                header_retry_after = e.headers.get("Retry-After") or e.headers.get("retry-after")
                if header_retry_after:
                    with contextlib.suppress(ValueError, TypeError):
                        retry_after = min(float(header_retry_after), MAX_RETRY_AFTER)
                retry_after = min(retry_after, MAX_RETRY_AFTER)
                last_error = typed_error
                time.sleep(retry_after)
                continue

            if e.code >= 500 and attempt < MAX_RETRIES:
                last_error = typed_error
                time.sleep(RETRY_DELAY)
                continue

            raise typed_error from None

        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES:
                last_error = LLMConnectionError(f"Connection failed: {e.reason}")
                time.sleep(RETRY_DELAY)
                continue
            raise LLMConnectionError(f"Connection failed: {e.reason}") from e

    raise last_error or LLMProviderError("max retries exhausted")


def call_with_fallback(
    messages: list[dict],
    role: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Call LLM with role-based model selection and fallback chain.

    Args:
        messages: Message list.
        role: Pipeline role key (e.g. "round_1_explore"). If None, uses sensenova/deepseek-v4-flash.
        temperature: Sampling temperature.
        max_tokens: Max output tokens.
        timeout: Request timeout.

    Returns:
        Response text.

    Raises:
        LLMProviderError if all models in the fallback chain fail.
    """
    if role and role in PIPELINE_MODELS:
        primary = PIPELINE_MODELS[role]
    else:
        primary = {"provider": "sensenova", "model": "deepseek-v4-flash"}

    # Build attempt order: primary first, then fallback chain minus primary
    primary_key = f"{primary['provider']}/{primary['model']}"
    attempt_order = [primary] + [
        m for m in FALLBACK_CHAIN
        if f"{m['provider']}/{m['model']}" != primary_key
    ]

    last_error: Exception | None = None
    for model_entry in attempt_order:
        try:
            response = call_llm(
                messages,
                provider=model_entry["provider"],
                model=model_entry["model"],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            if response:
                return response
        except LLMProviderError as e:
            last_error = e
            continue

    raise LLMProviderError(
        f"All models exhausted for role '{role}'. Last error: {last_error}"
    )


def parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response text with multiple fallback strategies.

    Handles:
    - Direct JSON
    - ```json ... ``` code blocks
    - Bare { ... } objects
    - Common JSON formatting issues (single quotes, trailing commas, comments)

    Raises:
        JSONParseError if all strategies fail.
    """
    if not text or not text.strip():
        raise JSONParseError("LLM returned empty content")

    text = text.strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Extract from ```json ... ``` or ``` ... ```
    for marker in ["```json", "```"]:
        start = text.find(marker)
        if start >= 0:
            start += len(marker)
            end = text.find("```", start)
            if end > start:
                candidate = text[start:end].strip()
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass

    # 3. Find outermost { ... }
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        candidate = text[brace_start: brace_end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 4. Fix common issues and retry
    fixed = text
    fixed = fixed.replace("'", '"')
    fixed = re.sub(r"//[^\n]*", "", fixed)
    fixed = re.sub(r",\s*}", "}", fixed)
    fixed = re.sub(r",\s*]", "]", fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    raise JSONParseError(f"Cannot parse JSON from LLM response:\n{text[:500]}")
