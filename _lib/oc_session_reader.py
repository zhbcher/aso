"""_lib/oc_session_reader.py — OpenClaw 会话读取器

适配自 KLXZ evolve-skill-v4 _lib/session_reader.py。
从 OpenClaw 的会话数据生成标准化 trace。
"""

import json
import os
import datetime as dt
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from _lib.path_utils import WORKSPACE_ROOT
from _lib.time_utils import utcnow_iso


def load_recent_traces(limit: int = 20) -> List[Dict]:
    """从 OpenClaw 工作区读取会话数据并转换为 trace。

    数据源:
    1. `~/.openclaw/sessions/` 下的会话文件
    2. workspace 下的 session 相关文件
    3. 无数据时返回空列表

    Args:
        limit: 最大返回 trace 数量。

    Returns:
        符合 trace_schema v1 的 trace 列表。
    """
    traces = []

    # 方法 1: 尝试从 OpenClaw sessions 目录读取
    openclaw_dir = Path.home() / ".openclaw"
    sessions_dir = openclaw_dir / "sessions"

    if sessions_dir.exists():
        json_files = sorted(
            sessions_dir.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )[:limit]

        for fpath in json_files:
            try:
                trace = _parse_session_file(fpath)
                if trace:
                    traces.append(trace)
            except Exception:
                continue

    # 方法 2: 尝试从 session-logs skill 的数据目录读取
    if not traces:
        session_logs_dir = WORKSPACE_ROOT / "skills" / "session-logs"
        if session_logs_dir.exists():
            for f in session_logs_dir.glob("**/*.json"):
                try:
                    trace = _parse_session_file(f)
                    if trace:
                        traces.append(trace)
                except Exception:
                    continue

    return traces[-limit:] if traces else []


def _parse_session_file(fpath: Path) -> Optional[Dict]:
    """解析单个会话文件，转换为 trace 格式。

    Args:
        fpath: 会话 JSON 文件路径。

    Returns:
        标准化的 trace dict，或 None 如果解析失败。
    """
    if not fpath.exists() or fpath.stat().st_size == 0:
        return None

    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

    # 处理不同的文件格式
    if isinstance(data, list):
        return _parse_jsonl_style(fpath, data)
    elif isinstance(data, dict):
        return _parse_dict_session(data, fpath)

    return None


def _parse_jsonl_style(fpath: Path, entries: List) -> Optional[Dict]:
    """解析类似 JSONL 的会话文件（数组格式）。

    参考 KLXZ 的 JSONL 格式：
    - type: "message", "function_call", "function_call_result"
    """
    if not entries:
        return None

    messages = []
    tool_calls = []
    reasoning_count = 0
    first_timestamp = None
    total_tokens = 0
    total_duration = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        entry_type = entry.get("type", "")
        ts = entry.get("timestamp")

        if ts:
            if first_timestamp is None:
                first_timestamp = ts

        if entry_type == "message":
            role = entry.get("role", "unknown")
            content = entry.get("content", "")
            text = str(content)[:500] if content else ""
            messages.append({"role": role, "text": text, "timestamp": ts})

        elif entry_type == "function_call":
            name = entry.get("name", entry.get("tool", "unknown"))
            tool_calls.append({
                "id": name,
                "timestamp": ts,
                "status": None,
                "duration_ms": 0,
                "tokens": 0,
            })

        elif entry_type == "function_call_result":
            for tc in reversed(tool_calls):
                call_id = entry.get("callId", "")
                if tc.get("call_id") == call_id or call_id == "":
                    tc["status"] = entry.get("status", "success")
                    result = entry.get("result", {})
                    if isinstance(result, dict):
                        tc["tokens"] = result.get("tokens", 0)
                    break

    # Compute stats
    total_calls = len(tool_calls)
    failed_calls = sum(1 for tc in tool_calls if tc.get("status") == "error")

    # Build trace
    skill_traces = []
    for tc in tool_calls:
        skill_traces.append({
            "id": tc["id"],
            "version": "v1",
            "duration_ms": tc.get("duration_ms", 0),
            "tokens": tc.get("tokens", 0),
            "success": tc.get("status") != "error",
            "retry_count": 0,
            "error": None if tc.get("status") != "error" else "error",
        })

    ts_str = (
        dt.datetime.fromtimestamp(first_timestamp / 1000, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
        if first_timestamp
        else utcnow_iso()
    )

    return {
        "task_id": fpath.stem,
        "timestamp": ts_str,
        "source": "openclaw_session",
        "total_tokens": total_tokens,
        "total_duration_ms": total_duration,
        "agent": {
            "id": "agent",
            "version": "v1",
            "success": (total_calls - failed_calls) / max(total_calls, 1) >= 0.8,
            "latency_ms": total_duration,
        },
        "skills": skill_traces,
        "memory": {
            "hit_rate": round((total_calls - failed_calls) / max(total_calls, 1), 2),
            "latency_ms": int(total_duration / max(total_calls, 1)) if total_calls else 0,
        },
        "models_used": [],
        "tool_call_count": total_calls,
        "tool_call_success_rate": round(
            (total_calls - failed_calls) / max(total_calls, 1), 3
        ) if total_calls else 1.0,
        "message_count": len(messages),
    }


def _parse_dict_session(data: Dict, fpath: Path) -> Optional[Dict]:
    """解析字典格式的会话数据。"""
    skills = data.get("skills", data.get("tools", []))
    if not isinstance(skills, list):
        skills = []

    skill_traces = []
    total_tokens = data.get("total_tokens", 0)
    total_duration = data.get("total_duration_ms", 0)

    for s in skills:
        if isinstance(s, dict):
            skill_traces.append({
                "id": s.get("id", s.get("name", "unknown")),
                "version": s.get("version", "v1"),
                "duration_ms": s.get("duration_ms", 0),
                "tokens": s.get("tokens", 0),
                "success": s.get("success", True),
                "retry_count": s.get("retry_count", 0),
                "error": s.get("error"),
            })

    agent_data = data.get("agent", data.get("planner", {}))
    success_count = sum(1 for s in skill_traces if s["success"])
    total_count = len(skill_traces) if skill_traces else 1

    return {
        "task_id": data.get("task_id", fpath.stem),
        "timestamp": data.get("timestamp", utcnow_iso()),
        "source": "openclaw_session",
        "total_tokens": total_tokens,
        "total_duration_ms": total_duration,
        "agent": {
            "id": agent_data.get("id", "agent"),
            "version": agent_data.get("version", "v1"),
            "success": success_count / max(total_count, 1) >= 0.8,
            "latency_ms": agent_data.get("latency_ms", 0),
        },
        "skills": skill_traces,
        "memory": {
            "hit_rate": data.get("memory", {}).get("hit_rate", success_count / max(total_count, 1)),
            "latency_ms": data.get("memory", {}).get("latency_ms", 0),
        },
        "models_used": data.get("models_used", []),
        "tool_call_count": total_count,
        "tool_call_success_rate": round(
            success_count / max(total_count, 1), 3
        ) if total_count else 1.0,
        "message_count": data.get("message_count", 0),
    }