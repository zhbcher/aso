"""_lib/config_loader.py — YAML config loader for ASO.

Loads config.yaml with PyYAML or fallback YAML parser.
Provides typed access to provider, pipeline, and fallback settings.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_ASO_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_PATH = _ASO_DIR / "config.yaml"

# Cache
_config: dict[str, Any] | None = None


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML, trying PyYAML first with regex fallback."""
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore[import-untyped]
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return _parse_yaml_simple(path)


def _parse_yaml_simple(path: Path) -> dict[str, Any]:
    """Basic YAML parser fallback using raw line parsing."""
    result: dict[str, Any] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return result
    stack: list[dict[str, Any]] = [result]
    key_path: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        while len(key_path) > 0 and indent <= len(key_path) * 2 - 2:
            key_path.pop()
            stack.pop()
        if stripped.endswith(":"):
            key = stripped[:-1]
            key_path.append(key)
            new_dict: dict[str, Any] = {}
            stack[-1][key] = new_dict
            stack.append(new_dict)
        elif ":" in stripped:
            k, v = stripped.split(":", 1)
            k = k.strip()
            v = v.strip()
            # List value?
            if v == "" and len(stack) > 0:
                stack[-1][k] = []
            elif v.startswith("[") and v.endswith("]"):
                import json
                try:
                    stack[-1][k] = json.loads(v)
                except Exception:
                    stack[-1][k] = v
            else:
                stack[-1][k] = v
        elif stripped.startswith("- "):
            val = stripped[2:]
            if stack:
                for d in reversed(stack):
                    last_key = None
                    for sk in reversed(list(d.keys())):
                        last_key = sk
                        break
                    if last_key and isinstance(d.get(last_key), list):
                        d.setdefault(last_key, []).append(val)
                        break
                    if isinstance(d, list):
                        d.append(val)
                        break
    return result


def _ensure_defaults(config: dict[str, Any]) -> None:
    """Ensure config has a 'defaults' key for backward compatibility.
    If 'defaults' is missing but 'timeouts' exists, populate defaults from timeouts.
    """
    if "defaults" not in config:
        timeouts = config.get("timeouts", {})
        config["defaults"] = {
            "timeout_seconds": timeouts.get("default", 60),
            "max_retries": timeouts.get("max_retries", 2),
            "retry_delay_seconds": timeouts.get("retry_delay", 1.0),
            "max_429_retries": timeouts.get("max_429_retries", 3),
            "initial_backoff_429_seconds": timeouts.get("initial_backoff_429", 2.0),
            "max_retry_after_seconds": timeouts.get("max_retry_after", 60),
        }


def reload_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Force reload config from disk and return parsed data."""
    global _config
    path = Path(config_path) if config_path else _CONFIG_PATH
    data = _load_yaml(path)
    _ensure_defaults(data)
    _config = data
    return _config


def get_config() -> dict[str, Any]:
    """Get parsed configuration (cached after first load)."""
    global _config
    if _config is None:
        data = _load_yaml(_CONFIG_PATH)
        _ensure_defaults(data)
        _config = data
    return _config


# === Strongly typed accessors ===


def get_providers() -> dict[str, Any]:
    """Get provider definitions from config."""
    return get_config().get("providers", {})


def get_pipeline_models() -> dict[str, dict[str, str]]:
    """Get pipeline model assignments."""
    return get_config().get("pipeline_models", {})


def get_fallback_chain() -> list[dict[str, str]]:
    """Get fallback model chain."""
    return get_config().get("fallback_chain", [])


def get_default(key: str, default: Any = None) -> Any:
    """Get a default setting value.
    Checks 'defaults' first, then falls back to legacy locations like 'timeouts'.
    """
    config = get_config()
    if "defaults" in config:
        return config["defaults"].get(key, default)
    # Backward compatible: timeouts.*
    timeouts = config.get("timeouts", {})
    mapping = {
        "timeout_seconds": "default",
        "max_retries": "max_retries",
        "retry_delay_seconds": "retry_delay",
        "max_429_retries": "max_429_retries",
        "initial_backoff_429_seconds": "initial_backoff_429",
        "max_retry_after_seconds": "max_retry_after",
    }
    if key in mapping:
        return timeouts.get(mapping[key], default)
    return default


def get_pipeline_default(key: str, default: Any = None) -> Any:
    """Get a pipeline default setting."""
    return get_config().get("pipeline_defaults", {}).get(key, default)
