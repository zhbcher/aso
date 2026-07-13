"""_lib/oc_llm_client.py — OpenClaw 版 LLM 调用客户端

适配自 KLXZ evolve-skill-v4 _lib/klzm_client.py。
将 KLXZ 的 klzm-proxy 调用改为直接调用 OpenClaw 配置的 LLM provider。
支持多模型轮换 + fallback 链 + 重试 + 429 退避。
"""

import json
import os
import re
import time
import urllib.request
import urllib.error
from typing import Optional, List, Dict

# === OpenClaw model providers ===
# Models available in OpenClaw (reading from env vars)
# Configured in openclaw.json skills.entries.moa.env

PROVIDERS = {
    "sensenova": {
        "base_url": "https://api.sensenova.cn/v1/chat/completions",
        "api_key_env": "SENSENOVA_API_KEY",
        "models": ["deepseek-v4-flash", "sensenova-6.7-flash-lite"],
    },
    "nvidia": {
        "base_url": "https://api.nvidia.com/v1/chat/completions",
        "api_key_env": "NVIDIA_API_KEY",
        "models": ["stepfun-ai/step-3.7-flash", "stepfun-ai/step-3.5-flash", "nvidia/llama-3.3-nemotron-super-49b-v1"],
    },
    "agnes": {
        "base_url": "https://api.agnesai.com/v1/chat/completions",
        "api_key_env": "AGNES_API_KEY",
        "models": ["agnes-2.0-flash"],
    },
}

# Role-based model assignment for bilevel generator (4 rounds)
PIPELINE_MODELS = {
    "round_1_explore": {"provider": "sensenova", "model": "deepseek-v4-flash"},
    "round_2_critique": {"provider": "nvidia", "model": "stepfun-ai/step-3.7-flash"},
    "round_3_specify": {"provider": "sensenova", "model": "deepseek-v4-flash"},
    "round_4_review": {"provider": "nvidia", "model": "stepfun-ai/step-3.5-flash"},
}

# Fallback chain: if primary model fails, try next in this order
FALLBACK_CHAIN = [
    {"provider": "sensenova", "model": "deepseek-v4-flash"},
    {"provider": "nvidia", "model": "stepfun-ai/step-3.7-flash"},
    {"provider": "nvidia", "model": "stepfun-ai/step-3.5-flash"},
    {"provider": "sensenova", "model": "sensenova-6.7-flash-lite"},
]

DEFAULT_TIMEOUT = 60  # seconds
MAX_RETRIES = 2
RETRY_DELAY = 1.0
MAX_429_RETRIES = 3
INITIAL_BACKOFF_429 = 2.0
MAX_RETRY_AFTER = 60


def _get_api_key(provider: str) -> str:
    """Get API key for a given provider from environment variables."""
    provider_config = PROVIDERS.get(provider)
    if not provider_config:
        return ""
    return os.environ.get(provider_config["api_key_env"], "")


def _clean_think_tags(text: str) -> str:
    """Remove  thinking... response blocks from model output."""
    if not text:
        return ""
    cleaned = re.sub(r" thinking[\s\S]*? response", "", cleaned, flags=re.IGNORECASE) if False else text
    cleaned = re.sub(r"<think>[\s\S]*?<\/think>", "", cleaned, flags=re.IGNORECASE)
    # Also handle  and  (OpenClaw reasoning markers)
    cleaned = re.sub(r"<thinking>[\s\S]*?<\/thinking>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<Thought>[\s\S]*?<\/Thought>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def call_llm(
    messages: List[Dict],
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
        RuntimeError if API call fails.
    """
    provider_config = PROVIDERS.get(provider)
    if not provider_config:
        raise RuntimeError(f"Unknown provider: {provider}")

    api_key = _get_api_key(provider)
    if not api_key:
        raise RuntimeError(f"{provider_config['api_key_env']} not set")

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

    last_error = None
    retry_429_count = 0
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                msg = result.get("choices", [{}])[0].get("message", {})
                content = msg.get("content", "")
                if content:
                    content = _clean_think_tags(content)
                return content.strip() if content else ""
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            if e.code == 429 and retry_429_count < MAX_429_RETRIES:
                retry_429_count += 1
                retry_after = INITIAL_BACKOFF_429 * (2 ** (retry_429_count - 1))
                header_retry_after = e.headers.get("Retry-After") or e.headers.get("retry-after")
                if header_retry_after:
                    try:
                        retry_after = min(float(header_retry_after), MAX_RETRY_AFTER)
                    except (ValueError, TypeError):
                        pass
                retry_after = min(retry_after, MAX_RETRY_AFTER)
                last_error = RuntimeError(f"HTTP 429: {error_body[:200]}")
                time.sleep(retry_after)
                req = urllib.request.Request(
                    provider_config["base_url"],
                    data=json.dumps(body).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    method="POST",
                )
                continue
            if e.code >= 500 and attempt < MAX_RETRIES:
                last_error = RuntimeError(f"HTTP {e.code}: {error_body[:300]}")
                time.sleep(RETRY_DELAY)
                req = urllib.request.Request(
                    provider_config["base_url"],
                    data=json.dumps(body).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    method="POST",
                )
                continue
            raise RuntimeError(f"HTTP {e.code}: {error_body[:300]}")
        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES:
                last_error = RuntimeError(f"Connection failed: {e.reason}")
                time.sleep(RETRY_DELAY)
                req = urllib.request.Request(
                    provider_config["base_url"],
                    data=json.dumps(body).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    method="POST",
                )
                continue
            raise RuntimeError(f"Connection failed: {e.reason}")

    raise last_error or RuntimeError("max retries exhausted")


def call_with_fallback(
    messages: List[Dict],
    role: Optional[str] = None,
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
        RuntimeError if all models in the fallback chain fail.
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

    last_error = None
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
        except RuntimeError as e:
            last_error = e
            continue

    raise RuntimeError(
        f"All models exhausted for role '{role}'. Last error: {last_error}"
    )


def parse_json_response(text: str) -> Dict:
    """Parse JSON from LLM response text with multiple fallback strategies.

    Handles:
    - Direct JSON
    - ```json ... ``` code blocks
    - Bare { ... } objects
    - Common JSON formatting issues (single quotes, trailing commas, comments)
    """
    if not text or not text.strip():
        raise ValueError("LLM returned empty content")

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

    raise ValueError(f"Cannot parse JSON from LLM response:\n{text[:500]}")