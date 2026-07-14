"""_lib/path_utils.py — OpenClaw 版路径常量

适配自 KLXZ evolve-skill-v4 _lib/path_utils.py。
将 KLXZ 的 ~/.kunlunxiaozhi 路径改为 OpenClaw workspace 路径。
"""

import os
from pathlib import Path

HOME = Path.home()

# OpenClaw workspace root
WORKSPACE_ROOT = Path(os.environ.get("OPENCLAW_WORKSPACE", HOME / ".openclaw" / "workspace"))

# Evolve skill self directory (this file is at _lib/path_utils.py, go up 2 levels)
EVOLVE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent

# Evolve internal directories
STATE_DIR = EVOLVE_DIR / "state"
BACKUPS_DIR = EVOLVE_DIR / "_backups"
GENERATOR_DIR = EVOLVE_DIR / "generator"

# State files
MANIFESTS_FILE = STATE_DIR / "manifests.json"
TRACE_STORE_FILE = STATE_DIR / "trace_store.json"
OPTIMIZATION_MEMORY_FILE = STATE_DIR / "optimization_memory.json"

# Evolution state (ASO v2)
EVOLUTION_DIR = STATE_DIR / "evolution"
EVOLUTION_SESSIONS_DIR = EVOLUTION_DIR / "sessions"
EVOLUTION_EVENTS_DIR = EVOLUTION_DIR / "events"
EVOLUTION_INDEX_FILE = EVOLUTION_DIR / "index.json"
EVOLUTION_EVENTS_FILE = EVOLUTION_EVENTS_DIR / "journal.jsonl"
EVOLUTION_POLICY_FILE = STATE_DIR / "evolution-policy.yaml"

# Config files
POLICY_FILE = EVOLVE_DIR / "evolution-policy.yaml"
TRACE_SCHEMA_JSON = EVOLVE_DIR / "trace_schema.json"
TRACE_SCHEMA_YAML = EVOLVE_DIR / "trace_schema.yaml"

# Hot-reload trigger file
RELOAD_TRIGGER = EVOLVE_DIR / ".reload_trigger"

# Skills base directory
SKILLS_DIR = WORKSPACE_ROOT / "skills"

# Sensitive files that must never be modified by evolution
PROTECTED_FILES = [
    WORKSPACE_ROOT / "openclaw.json",
    WORKSPACE_ROOT / "AGENTS.md",
    WORKSPACE_ROOT / "SOUL.md",
    WORKSPACE_ROOT / "USER.md",
    WORKSPACE_ROOT / "MEMORY.md",
    WORKSPACE_ROOT / ".openclaw" / "secret.json",
]


def ensure_dirs():
    """Ensure all required directories exist."""
    for d in [STATE_DIR, BACKUPS_DIR, GENERATOR_DIR, EVOLUTION_SESSIONS_DIR, EVOLUTION_EVENTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def get_skill_dirs() -> list[Path]:
    """Get all skill directories from the OpenClaw workspace."""
    if not SKILLS_DIR.exists():
        return []
    return sorted([d for d in SKILLS_DIR.iterdir() if d.is_dir()])
